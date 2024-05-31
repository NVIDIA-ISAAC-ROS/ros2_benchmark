// SPDX-FileCopyrightText: NVIDIA CORPORATION & AFFILIATES
// Copyright (c) 2023-2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
// http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.
//
// SPDX-License-Identifier: Apache-2.0

#include "ros2_benchmark/data_loader_node.hpp"

#include <fstream>
#include <sstream>
#include <iomanip>

#include "ros2_benchmark_interfaces/msg/topic_message_timestamp_array.hpp"

namespace ros2_benchmark
{

DataLoaderNode::DataLoaderNode(const rclcpp::NodeOptions & options)
: rclcpp::Node("DataLoader", options),
  service_callback_group_{create_callback_group(rclcpp::CallbackGroupType::Reentrant)},
  set_data_service_{
    create_service<ros2_benchmark_interfaces::srv::SetData>(
      "set_data",
      std::bind(
        &DataLoaderNode::SetDataServiceCallback,
        this,
        std::placeholders::_1,
        std::placeholders::_2),
      rmw_qos_profile_default,
      service_callback_group_)},
  start_loading_service_{
    create_service<ros2_benchmark_interfaces::srv::StartLoading>(
      "start_loading",
      std::bind(
        &DataLoaderNode::StartLoadingServiceCallback,
        this,
        std::placeholders::_1,
        std::placeholders::_2),
      rmw_qos_profile_default,
      service_callback_group_)},
  stop_loading_service_{
    create_service<ros2_benchmark_interfaces::srv::StopLoading>(
      "stop_loading",
      std::bind(&DataLoaderNode::StopLoadingServiceCallback, this, std::placeholders::_1,
      std::placeholders::_2),
      rmw_qos_profile_default, service_callback_group_)},
  get_topic_message_timestamps_service_{
    create_service<ros2_benchmark_interfaces::srv::GetTopicMessageTimestamps>(
      "get_topic_message_timestamps",
      std::bind(
        &DataLoaderNode::GetTopicMessageTimestampsSereviceCallback,
        this,
        std::placeholders::_1,
        std::placeholders::_2),
      rmw_qos_profile_default,
      service_callback_group_)},
  publisher_period_ms_(declare_parameter<int64_t>("publisher_period_ms", 10))
{
}

void DataLoaderNode::SetDataServiceCallback(
  const ros2_benchmark_interfaces::srv::SetData::Request::SharedPtr request,
  ros2_benchmark_interfaces::srv::SetData::Response::SharedPtr response)
{
  topic_message_timestamps_.clear();
  rosbag_path_ = request->data_path;
  RCLCPP_INFO(get_logger(), "Set the rosbag file to be: %s", rosbag_path_.c_str());
  try {
    OpenRosbagFile();
  } catch (const std::runtime_error & error) {
    RCLCPP_ERROR(get_logger(), "Failed to open the rosbag: %s", error.what());
    response->success = false;
    return;
  }
  if (is_rosbag_compressed_) {
    RCLCPP_INFO(get_logger(), "Detected that the rosbag was zstd-message-compressed.");
  }

  // Create Publishers
  auto topics = rosbag_reader_.get_all_topics_and_types();
  for (const auto & topic : topics) {
    if (publishers_.find(topic.name) != publishers_.end()) {
      continue;
    }

    // Create dedicated TF publishers if required
    if ((request->publish_tf_messages && topic.name == "/tf") ||
      (request->publish_tf_static_messages && topic.name == "/tf_static"))
    {
      rclcpp::QoS tf_qos = kBufferQoS;
      std::shared_ptr<rclcpp::GenericPublisher> tf_pub = create_generic_publisher(
        topic.name,
        topic.type,
        tf_qos.reliable().transient_local());
      tf_publishers_.insert(std::make_pair(topic.name, tf_pub));
    }

    // Use a relative topic name to create a publisher so namespace can be
    // prepended correctly
    const std::string relative_topic_name =
      (topic.name[0] == '/') ? topic.name.substr(1) : topic.name;
    std::shared_ptr<rclcpp::GenericPublisher> pub =
      create_generic_publisher(relative_topic_name, topic.type, kBufferQoS);

    publishers_.insert(std::make_pair(topic.name, pub));
    topic_message_timestamps_[pub->get_topic_name()] = {};

    RCLCPP_INFO(
      get_logger(),
      "Created a publisher: topic=\"%s\", type=\"%s\"",
      pub->get_topic_name(), topic.type.c_str());
  }

  // Store message timestamps for each topic
  bool first_message = true;
  while (rosbag_reader_.has_next()) {
    std::shared_ptr<rosbag2_storage::SerializedBagMessage> message =
      rosbag_reader_.read_next();

    if (publishers_.count(message->topic_name) == 0) {
      RCLCPP_ERROR(
        get_logger(),
        "Failed to find a publisher, topic=\"%s\"",
        message->topic_name.c_str());
      continue;
    }

    // Update the first timestamp value if needed
    if (first_message) {
      first_message = false;
      first_timestamp_ns_ = message->time_stamp;
      last_timestamp_ns_ = message->time_stamp;
    } else {
      if (message->time_stamp < first_timestamp_ns_) {
        first_timestamp_ns_ = message->time_stamp;
      }
      if (message->time_stamp > last_timestamp_ns_) {
        last_timestamp_ns_ = message->time_stamp;
      }
    }

    // Store the message's rosbag-recorded timestamp
    const std::string remapped_topic_name = publishers_[message->topic_name]->get_topic_name();
    topic_message_timestamps_[remapped_topic_name].push_back(message->time_stamp);

    // Publish TF messages if required
    if ((request->publish_tf_messages && message->topic_name == "/tf") ||
      (request->publish_tf_static_messages && message->topic_name == "/tf_static"))
    {
      PublishMessage(tf_publishers_[message->topic_name], message);
      RCLCPP_INFO(
        get_logger(),
        "Published a TF message to topic=\"%s\"",
        message->topic_name.c_str());
    }
  }

  response->success = true;
}

void DataLoaderNode::StartLoadingServiceCallback(
  const ros2_benchmark_interfaces::srv::StartLoading::Request::SharedPtr request,
  ros2_benchmark_interfaces::srv::StartLoading::Response::SharedPtr response)
{
  played_message_count_ = 0;
  stop_playing_ = false;

  int64_t true_start_time_ns = first_timestamp_ns_;
  if (request->start_time_offset_ns >= 0) {
    true_start_time_ns = first_timestamp_ns_ + request->start_time_offset_ns;
  }

  int64_t true_end_time_ns = last_timestamp_ns_;
  if (request->end_time_offset_ns >= 0) {
    true_end_time_ns = first_timestamp_ns_ + request->end_time_offset_ns;
  }

  if (topic_message_timestamps_.size() == 0) {
    RCLCPP_ERROR(
      get_logger().get_child("StartLoadingServiceCallback"),
      "No rosbag file was successfully loaded. "
      "A service request to \"set_data\" must be sent before start_loading service "
      "can proceed.");
    response->success = false;
    return;
  }

  // Read the rosbag file from the beginning
  OpenRosbagFile();
  int64_t timestamp_offset = this->get_clock()->now().nanoseconds() - first_timestamp_ns_;

  // Publish messages at the configured frequency
  while (true) {
    {
      // Check if it is requested to stop loading
      std::lock_guard<std::mutex> lock(stop_playing_mutex_);
      if (stop_playing_) {
        break;
      }
    }

    if (!rosbag_reader_.has_next()) {
      if (!request->repeat_data) {
        break;
      }
      // Repeat loading data if requestd
      OpenRosbagFile();
      timestamp_offset = this->get_clock()->now().nanoseconds() - first_timestamp_ns_;
    }

    std::shared_ptr<rosbag2_storage::SerializedBagMessage> message =
      rosbag_reader_.read_next();

    if (publishers_.count(message->topic_name) == 0) {
      RCLCPP_ERROR(
        get_logger(),
        "[DataLoaderNode] Failed to find a publisher, topic=\"%s\"",
        message->topic_name.c_str());
      stop_playing_ = true;
      response->success = false;
      return;
    }

    if ((message->time_stamp < true_start_time_ns) ||
      (message->time_stamp > true_end_time_ns))
    {
      continue;
    }

    if (request->publish_in_real_time) {
      while (true) {
        rclcpp::Time now = this->get_clock()->now();
        int64_t diff_to_next_timestamp =
          (message->time_stamp + timestamp_offset) - now.nanoseconds();
        if (diff_to_next_timestamp <= 0) {
          break;
        }
        rclcpp::sleep_for(std::chrono::nanoseconds(diff_to_next_timestamp));
      }
    }

    PublishMessage(publishers_[message->topic_name], message);
    played_message_count_++;

    if (!request->publish_in_real_time) {
      std::this_thread::sleep_for(std::chrono::milliseconds(publisher_period_ms_));
    }
  }
  rosbag_reader_.close();

  {
    std::lock_guard<std::mutex> lock(stop_playing_mutex_);
    stop_playing_ = true;
  }
  response->played_message_count = played_message_count_;
  response->success = true;

  auto topic_message_timestamps_message_list =
    CreateTopicMessageTimestampArrayMessageList(true_start_time_ns, true_end_time_ns);
  response->topic_message_timestamps.insert(
    response->topic_message_timestamps.end(),
    topic_message_timestamps_message_list.begin(),
    topic_message_timestamps_message_list.end());
}

void DataLoaderNode::StopLoadingServiceCallback(
  const ros2_benchmark_interfaces::srv::StopLoading::Request::SharedPtr,
  ros2_benchmark_interfaces::srv::StopLoading::Response::SharedPtr)
{
  std::lock_guard<std::mutex> lock(stop_playing_mutex_);
  stop_playing_ = true;
}

void DataLoaderNode::GetTopicMessageTimestampsSereviceCallback(
  const ros2_benchmark_interfaces::srv::GetTopicMessageTimestamps::Request::SharedPtr request,
  ros2_benchmark_interfaces::srv::GetTopicMessageTimestamps::Response::SharedPtr response)
{
  if (topic_message_timestamps_.size() == 0) {
    RCLCPP_ERROR(
      get_logger(),
      "[DataLoaderNode] No topic timestamps were available");
    response->success = false;
    return;
  }

  int64_t true_start_time_ns = first_timestamp_ns_;
  if (request->start_time_offset_ns >= 0) {
    true_start_time_ns = first_timestamp_ns_ + request->start_time_offset_ns;
  }

  int64_t true_end_time_ns = last_timestamp_ns_;
  if (request->end_time_offset_ns >= 0) {
    true_end_time_ns = first_timestamp_ns_ + request->end_time_offset_ns;
  }

  auto topic_message_timestamps_message_list =
    CreateTopicMessageTimestampArrayMessageList(true_start_time_ns, true_end_time_ns);
  response->topic_message_timestamps.insert(
    response->topic_message_timestamps.end(),
    topic_message_timestamps_message_list.begin(),
    topic_message_timestamps_message_list.end());
  response->success = true;
}

std::vector<int64_t> FilterValuesByRange(
  const std::vector<int64_t> & values,
  const int64_t start,
  const int64_t end)
{
  std::vector<int64_t> filtered;
  for (const auto value : values) {
    if (value >= start && value <= end) {
      filtered.push_back(value);
    }
  }
  return filtered;
}

std::vector<ros2_benchmark_interfaces::msg::TopicMessageTimestampArray>
DataLoaderNode::CreateTopicMessageTimestampArrayMessageList(
  const int64_t start_time_ns,
  const int64_t end_time_ns)
{
  std::vector<ros2_benchmark_interfaces::msg::TopicMessageTimestampArray> message_list;
  for (const auto &[topic_name, recorded_timestamps] : topic_message_timestamps_) {
    ros2_benchmark_interfaces::msg::TopicMessageTimestampArray topic_timestamps{};
    topic_timestamps.topic_name = topic_name;
    topic_timestamps.timestamps_ns = FilterValuesByRange(
      recorded_timestamps, start_time_ns, end_time_ns);
    message_list.push_back(topic_timestamps);
  }
  return message_list;
}

void DataLoaderNode::OpenRosbagFile()
{
  rcpputils::fs::path rosbag_path(rosbag_path_);
  if (!rosbag_path.exists()) {
    std::stringstream error_msg;
    error_msg << "Could not load a rosbag file. " <<
      "\"" << rosbag_path.string() <<
      "\" does not exist";
    RCLCPP_ERROR(get_logger(), error_msg.str().c_str());
    throw std::runtime_error(error_msg.str().c_str());
  }

  // Open with default option to get the storage type (from storage_id in metadata)
  rosbag2_storage::StorageOptions trial_storage_options;
  trial_storage_options.uri = rosbag_path_;
  rosbag_reader_.open(trial_storage_options, {});

  rosbag2_storage::StorageOptions storage_options;
  storage_options.uri = rosbag_path_;
  storage_options.storage_id = rosbag_reader_.get_metadata().storage_identifier;

  RCLCPP_INFO(get_logger(), "Detected rosbag storage_id = %s", storage_options.storage_id.c_str());

  rosbag2_cpp::ConverterOptions converter_options;
  converter_options.input_serialization_format = "cdr";
  converter_options.output_serialization_format = "cdr";

  rosbag_reader_.close();
  rosbag_reader_.open(storage_options, converter_options);

  // Check the rosbag's compression formats
  std::string compression_format = rosbag_reader_.get_metadata().compression_format;
  transform(
    compression_format.begin(), compression_format.end(),
    compression_format.begin(), ::tolower);

  std::string compression_mode = rosbag_reader_.get_metadata().compression_mode;
  transform(
    compression_mode.begin(), compression_mode.end(),
    compression_mode.begin(), ::tolower);

  if ((compression_format == "zstd") && (compression_mode == "message")) {
    is_rosbag_compressed_ = true;
  } else {
    is_rosbag_compressed_ = false;
  }
}

void DataLoaderNode::PublishMessage(
  std::shared_ptr<rclcpp::GenericPublisher> publisher,
  std::shared_ptr<rosbag2_storage::SerializedBagMessage> message)
{
  if (is_rosbag_compressed_) {
    decompressor_.decompress_serialized_bag_message(message.get());
  }
  publisher->publish(rclcpp::SerializedMessage(*message->serialized_data));
}

DataLoaderNode::~DataLoaderNode()
{
  rosbag_reader_.close();
}

}  // namespace ros2_benchmark

// Register as a component
#include "rclcpp_components/register_node_macro.hpp"
RCLCPP_COMPONENTS_REGISTER_NODE(ros2_benchmark::DataLoaderNode)
