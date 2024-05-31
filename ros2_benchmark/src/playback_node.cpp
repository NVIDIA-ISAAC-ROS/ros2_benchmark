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

#include "ros2_benchmark/playback_node.hpp"

#include <ament_index_cpp/get_package_share_directory.hpp>

#include "ros2_benchmark_interfaces/msg/timestamped_message_array.hpp"
#include "ros2_benchmark_interfaces/msg/topic_message_count.hpp"

using PlaybackMode = ros2_benchmark_interfaces::srv::PlayMessages::Request;

namespace ros2_benchmark
{

std_msgs::msg::Header GenerateHeaderFromKey(int64_t key)
{
  std_msgs::msg::Header header{};

  // Use the timestamp field to hold the unique, ordered key
  header.stamp.sec = key;
  return header;
}

PlaybackNode::PlaybackNode(
  const std::string & node_name,
  const rclcpp::NodeOptions & options)
: rclcpp::Node(node_name, options),
  service_callback_group_{create_callback_group(rclcpp::CallbackGroupType::MutuallyExclusive)},
  start_recording_service_{
    create_service<ros2_benchmark_interfaces::srv::StartRecording>(
      "start_recording",
      std::bind(
        &PlaybackNode::StartRecordingServiceCallback,
        this, std::placeholders::_1,
        std::placeholders::_2),
      rmw_qos_profile_default,
      service_callback_group_)},
  stop_recording_service_{
    create_service<ros2_benchmark_interfaces::srv::StopRecording>(
      "stop_recording",
      std::bind(
        &PlaybackNode::StopRecordingServiceCallback,
        this, std::placeholders::_1,
        std::placeholders::_2),
      rmw_qos_profile_default,
      service_callback_group_)},
  play_messages_service_{
    create_service<ros2_benchmark_interfaces::srv::PlayMessages>(
      "play_messages",
      std::bind(
        &PlaybackNode::PlayMessagesServiceCallback,
        this, std::placeholders::_1,
        std::placeholders::_2),
      rmw_qos_profile_default,
      service_callback_group_)},
  max_size_(std::numeric_limits<size_t>::max()),
  data_formats_(declare_parameter<std::vector<std::string>>(
      "data_formats",
      std::vector<std::string>())),
  timeline_topic_name_translations_(
    declare_parameter<std::vector<std::string>>(
      "timeline_topic_name_translations",
      std::vector<std::string>()))
{
}

PlaybackNode::PlaybackNode(const rclcpp::NodeOptions & options)
: PlaybackNode("PlaybackNode", options)
{
  if (data_formats_.empty()) {
    throw std::invalid_argument(
            "Empty data_formats, "
            "this needs to be set to match the data formats for the data to be buffered");
  }

  for (size_t index = 0; index < data_formats_.size(); index++) {
    CreateGenericPubSub(data_formats_[index], index);
  }
}

void PlaybackNode::CreateGenericPubSub(const std::string data_format, const size_t index)
{
  // Create a generic publisher
  std::shared_ptr<rclcpp::GenericPublisher> pub = this->create_generic_publisher(
    "input" + std::to_string(index),
    data_format,
    kQoS);

  generic_pubs_[index] = pub;
  RCLCPP_INFO(
    get_logger(), "Created a generic publisher: topic=\"%s\"",
    pub->get_topic_name());

  // Create a generic subscriber
  std::function<void(std::shared_ptr<rclcpp::SerializedMessage>)>
  generic_type_subscriber_callback =
    std::bind(
    &PlaybackNode::GenericTypeRecordingSubscriberCallback,
    this,
    std::placeholders::_1,
    index);

  std::shared_ptr<rclcpp::SubscriptionBase> sub = this->create_generic_subscription(
    "buffer/input" + std::to_string(index),     // topic name
    data_format,                                // message type in the form of "package/type"
    kBufferQoS,
    generic_type_subscriber_callback);

  subs_[index] = sub;
  RCLCPP_INFO(
    get_logger(), "Created a generic subscriber: topic=\"%s\"",
    sub->get_topic_name());

  // Create a serialized message buffer
  serialized_msg_buffers_[index] = std::vector<std::shared_ptr<rclcpp::SerializedMessage>>();
}

bool PlaybackNode::AreBuffersFull() const
{
  if (record_data_timeline_) {
    return false;
  }
  if (requested_buffer_length_ == 0) {
    if ((timestamps_to_messages_map_.size() > 0) &&
      (GetRecordedMessageCount() == GetTimestampsToMessagesCount()))
    {
      return true;
    }
    return false;
  }
  for (const auto & buffer : serialized_msg_buffers_) {
    if (buffer.second.size() < requested_buffer_length_) {
      return false;
    }
  }
  return true;
}

void PlaybackNode::ClearBuffers()
{
  for (auto & buffer : serialized_msg_buffers_) {
    buffer.second.clear();
  }
  timestamps_to_messages_map_.clear();
}

uint64_t PlaybackNode::GetRecordedMessageCount() const
{
  uint64_t message_count = 0;
  for (const auto & buffer : serialized_msg_buffers_) {
    message_count += buffer.second.size();
  }
  return message_count;
}

uint64_t PlaybackNode::GetRecordedMessageCount(size_t pub_index) const
{
  return serialized_msg_buffers_.at(pub_index).size();
}

uint64_t PlaybackNode::GetTimestampsToMessagesCount() const
{
  uint64_t count = 0;
  for (const auto & it : timestamps_to_messages_map_) {
    count += it.second.size();
  }
  return count;
}

bool PlaybackNode::PublishMessage(
  const size_t pub_index,
  const size_t message_index,
  const std::optional<std_msgs::msg::Header> & header = std::nullopt)
{
  const size_t buffer_size = serialized_msg_buffers_[pub_index].size();
  if (message_index >= buffer_size) {
    const std::string topic_name = generic_pubs_[pub_index]->get_topic_name();
    RCLCPP_ERROR(
      get_logger(),
      "Failed to publish message index %ld for topic %s. "
      "Total recorded messages = %ld",
      message_index, topic_name.c_str(), buffer_size);
    return false;
  }

  if (header) {
    // Update the sec field in the serialized message
    uint8_t * header_sec_ptr =
      const_cast<uint8_t *>(reinterpret_cast<const uint8_t *>(&header->stamp.sec));
    serialized_msg_buffers_[pub_index].at(message_index).get()->get_rcl_serialized_message().buffer[
      4] = *(header_sec_ptr);
    serialized_msg_buffers_[pub_index].at(message_index).get()->get_rcl_serialized_message().buffer[
      5] = *(header_sec_ptr + 1);
    serialized_msg_buffers_[pub_index].at(message_index).get()->get_rcl_serialized_message().buffer[
      6] = *(header_sec_ptr + 2);
    serialized_msg_buffers_[pub_index].at(message_index).get()->get_rcl_serialized_message().buffer[
      7] = *(header_sec_ptr + 3);
  }

  generic_pubs_[pub_index]->publish(
    *serialized_msg_buffers_[pub_index].at(message_index).get());
  return true;
}

void PlaybackNode::PublishGroupMessages(
  size_t message_index,
  const std_msgs::msg::Header & header)
{
  for (size_t pub_index = 0; pub_index < GetPublisherCount(); pub_index++) {
    if (revise_timestamps_as_message_ids_) {
      PublishMessage(pub_index, message_index, header);
    } else {
      PublishMessage(pub_index, message_index);
    }
    RCLCPP_DEBUG(
      get_logger(),
      "Publishing a serialized message: index=%ld, timestamp=%d",
      message_index, header.stamp.sec);
  }
}

void PlaybackNode::GenericTypeRecordingSubscriberCallback(
  std::shared_ptr<rclcpp::SerializedMessage> serialized_message_ptr,
  size_t buffer_index)
{
  if ((serialized_msg_buffers_[buffer_index].size() >= max_size_) ||
    (requested_buffer_length_ > 0 &&
    serialized_msg_buffers_[buffer_index].size() >= requested_buffer_length_))
  {
    RCLCPP_DEBUG(
      get_logger(), "Dropped a serialized message due to a full buffer");
    return;
  }
  // Add received serialized message to the buffer
  serialized_msg_buffers_[buffer_index].push_back(serialized_message_ptr);
  RCLCPP_DEBUG(
    get_logger(), "Added a serialized message to the buffer (%ld/%ld)",
    serialized_msg_buffers_[buffer_index].size(), requested_buffer_length_);

  if (record_data_timeline_) {
    int64_t now_ns = this->get_clock()->now().nanoseconds();
    size_t message_index = serialized_msg_buffers_[buffer_index].size() - 1;
    AddToTimestampsToMessagesMap(now_ns, buffer_index, message_index);
  }
}

void PlaybackNode::StartRecordingServiceCallback(
  const ros2_benchmark_interfaces::srv::StartRecording::Request::SharedPtr request,
  ros2_benchmark_interfaces::srv::StartRecording::Response::SharedPtr response)
{
  RCLCPP_INFO(get_logger(), "start_recording service began");

  stop_recording_ = false;
  requested_buffer_length_ = static_cast<size_t>(request->buffer_length);
  record_data_timeline_ = request->record_data_timeline;
  if (record_data_timeline_) {
    RCLCPP_INFO(get_logger(), "Enabled timeline recording");
  }
  ClearBuffers();

  // Store topic message timestamps if provided (passed by the controller from a
  // data loader nodee).
  if (!record_data_timeline_ && request->topic_message_timestamps.size() > 0) {
    for (const auto & topic_message_timestamps : request->topic_message_timestamps) {
      const std::string topic_name = topic_message_timestamps.topic_name;
      for (const auto &[sub_index, sub_ptr] : subs_) {
        const std::string sub_topic_name = sub_ptr->get_topic_name();

        // A topic translation is required if there are nodes between a data loader
        // node and the current node as their topic names will not match
        std::string sub_translated_topic_name = "";
        if (timeline_topic_name_translations_.size() > sub_index) {
          sub_translated_topic_name = timeline_topic_name_translations_[sub_index];
        }

        if (sub_topic_name == topic_name || sub_translated_topic_name == topic_name) {
          size_t message_index = 0;
          for (const auto timestamp : topic_message_timestamps.timestamps_ns) {
            AddToTimestampsToMessagesMap(timestamp, sub_index, message_index);
            message_index++;
          }
          break;
        }
      }
      RCLCPP_DEBUG(
        get_logger(),
        "No matching topic \"%s\" for storing its message timestamps",
        topic_name.c_str());
    }
  }

  // Wait for all messages being recorded or reaching timeout
  const auto service_start_time = std::chrono::system_clock::now();
  bool has_timeout = false;
  while (true) {
    {
      std::lock_guard<std::mutex> lock(stop_recording_mutex_);
      if (AreBuffersFull() || stop_recording_) {
        response->success = true;
        break;
      }
    }
    auto current_time = std::chrono::system_clock::now();
    if (current_time - service_start_time >= std::chrono::seconds{request->timeout}) {
      response->success = false;
      has_timeout = true;
      break;
    }

    std::this_thread::sleep_for(std::chrono::milliseconds(kThreadDelay));
  }

  {
    std::lock_guard<std::mutex> lock(stop_recording_mutex_);
    stop_recording_ = true;
  }

  // Respond with the number of messages recorded in each topic
  response->recorded_message_count = GetRecordedMessageCount();
  for (const auto &[sub_index, sub_ptr] : subs_) {
    ros2_benchmark_interfaces::msg::TopicMessageCount topic_message_count{};
    topic_message_count.topic_name = sub_ptr->get_topic_name();
    topic_message_count.message_count = GetRecordedMessageCount(sub_index);
    response->recorded_topic_message_counts.push_back(topic_message_count);
  }

  if (!record_data_timeline_ && has_timeout) {
    RCLCPP_ERROR(
      get_logger(),
      "start_recording service returned with a timeout (%ld meessages recorded)",
      response->recorded_message_count);
  }
}

void PlaybackNode::StopRecordingServiceCallback(
  const ros2_benchmark_interfaces::srv::StopRecording::Request::SharedPtr,
  ros2_benchmark_interfaces::srv::StopRecording::Response::SharedPtr)
{
  std::lock_guard<std::mutex> lock(stop_recording_mutex_);
  stop_recording_ = true;
}

void PlaybackNode::PlayMessagesServiceCallback(
  const ros2_benchmark_interfaces::srv::PlayMessages::Request::SharedPtr request,
  ros2_benchmark_interfaces::srv::PlayMessages::Response::SharedPtr response)
{
  revise_timestamps_as_message_ids_ = request->revise_timestamps_as_message_ids;
  switch (request->playback_mode) {
    case PlaybackMode::PLAYBACK_MODE_TIMELINE:
      RCLCPP_INFO(
        get_logger(),
        "Playing messages in the timeline playback mode");
      PlayMessagesTimelinePlayback(request, response);
      break;
    default:
      RCLCPP_INFO(
        get_logger(),
        "Playing messages in the looping/sweeping mode");
      PlayMessagesLoopingSweeping(request, response);
      break;
  }
}

void PlaybackNode::PlayMessagesTimelinePlayback(
  const ros2_benchmark_interfaces::srv::PlayMessages::Request::SharedPtr request,
  ros2_benchmark_interfaces::srv::PlayMessages::Response::SharedPtr response)
{
  (void)request;

  if (timestamps_to_messages_map_.size() == 0) {
    RCLCPP_ERROR(
      get_logger(),
      "Could not play messages in the timeline playback mode due to missing "
      "message timestamp information");
    response->success = false;
    return;
  }

  RCLCPP_INFO(
    get_logger(),
    "Start playing %ld/%ld messages in the timeline playback mode",
    GetRecordedMessageCount(),
    GetTimestampsToMessagesCount());

  rclcpp::Time initial_timestamp = this->get_clock()->now();
  int64_t timestamp_offset =
    initial_timestamp.nanoseconds() - timestamps_to_messages_map_.begin()->first;
  for (const auto &[next_timestamp, message_list] : timestamps_to_messages_map_) {
    while (true) {
      rclcpp::Time now = this->get_clock()->now();
      int64_t diff_to_next_timestamp = (next_timestamp + timestamp_offset) - now.nanoseconds();
      if (diff_to_next_timestamp > 0) {
        rclcpp::sleep_for(std::chrono::nanoseconds(diff_to_next_timestamp));
        continue;
      }
      // Now it's time to publish messages.
      for (const auto & pub_message_index_pair : message_list) {
        size_t pub_index = pub_message_index_pair.first;
        size_t message_index = pub_message_index_pair.second;
        if (!PublishMessage(pub_index, message_index)) {
          // This message was not published due to an error.
          continue;
        }

        // Using the current message count as a key for recording a start timestamp
        auto key = message_counter_++;
        if (!RecordStartTimestamp(key)) {
          RCLCPP_ERROR(get_logger(), "Failed to add start timestamp for key %d", key);
          response->success = false;
          return;
        }
      }
      break;
    }
  }

  // Respond with start timestamps (when messages were being sent)
  ros2_benchmark_interfaces::msg::TimestampedMessageArray response_timestamps{};
  for (auto it : start_timestamps_) {
    response_timestamps.keys.emplace_back(it.first);
    response_timestamps.timestamps_ns.emplace_back(
      std::chrono::duration_cast<std::chrono::nanoseconds>(
        it.second.time_since_epoch())
      .count());
  }
  response->timestamps = response_timestamps;
  response->success = true;

  start_timestamps_.clear();
}

void PlaybackNode::PlayMessagesLoopingSweeping(
  const ros2_benchmark_interfaces::srv::PlayMessages::Request::SharedPtr request,
  ros2_benchmark_interfaces::srv::PlayMessages::Response::SharedPtr response)
{
  // First, confirm that the expected number of buffered messages was greater than 0,
  // otherwise we have no messages to play
  if (requested_buffer_length_ <= 0) {
    RCLCPP_ERROR(
      get_logger(),
      "Could not play messages: buffer length was not greater than 0");
    response->success = false;
    return;
  }

  // Then, confirm that we have buffered the expected number of messages
  if (!AreBuffersFull()) {
    RCLCPP_ERROR(
      get_logger(),
      "Did not receive all %lu expected messages on each buffer before starting playback",
      requested_buffer_length_);
    response->success = false;
    return;
  }

  // Initialize message for return
  ros2_benchmark_interfaces::msg::TimestampedMessageArray timestamps{};

  // Initialize playback rate
  rclcpp::Rate rate{request->target_publisher_rate};

  // If requested message count was 0 or smaller, default to one pass through the buffer
  size_t message_count =
    (request->message_count > 0) ? request->message_count : requested_buffer_length_;

  // Publish requested number of messages by looping through buffer
  bool is_publisher_rate_met = true;
  for (size_t i = 0; i < message_count; ++i) {
    // Generate identifying key for the message
    auto key = message_counter_++;

    // Generate header using that key
    auto header = GenerateHeaderFromKey(key);

    // Publish message with generated header
    size_t message_index;
    if (request->playback_mode == PlaybackMode::PLAYBACK_MODE_SWEEPING) {
      if ((i / requested_buffer_length_) % 2 == 1) {
        message_index = requested_buffer_length_ - (i % requested_buffer_length_) - 1;
      } else {
        message_index = i % requested_buffer_length_;
      }
    } else {
      message_index = i % requested_buffer_length_;
    }
    PublishGroupMessages(message_index, header);

    if (!RecordStartTimestamp(key)) {
      RCLCPP_ERROR(get_logger(), "Failed to store start a timestamp for key %d", key);
      response->success = false;
      return;
    }

    // Delay according to requested playback rate
    if (!rate.sleep()) {
      if (is_publisher_rate_met) {
        is_publisher_rate_met = false;
        RCLCPP_WARN(
          get_logger(), "Couldn't maintain the requested playback rate at %0.2fHz",
          request->target_publisher_rate);
      }

      // Abort if requested to enforce the target publish rate
      if (request->enforce_publisher_rate) {
        RCLCPP_WARN(
          get_logger(), "Abort as to target store start a timestamp for key %d", key);
        response->success = false;
        return;
      }
    }
  }

  // Record the keys of each message
  for (auto it : start_timestamps_) {
    timestamps.keys.emplace_back(it.first);
    timestamps.timestamps_ns.emplace_back(
      // Convert to nanoseconds
      std::chrono::duration_cast<std::chrono::nanoseconds>(
        it.second.time_since_epoch())
      .count());
  }

  // Finally, mark success as true
  response->success = true;
  response->timestamps = timestamps;

  start_timestamps_.clear();
}

bool PlaybackNode::RecordStartTimestamp(const int64_t & message_key)
{
  // Record timestamp first, in case we need to wait to acquire mutex
  const auto timestamp{std::chrono::system_clock::now()};

  // If key already exists in start map, return false
  if (start_timestamps_.count(message_key) > 0) {
    return false;
  }

  // Add entry to start timestamps, marking as unmatched
  start_timestamps_[message_key] = timestamp;
  return true;
}

void PlaybackNode::AddToTimestampsToMessagesMap(
  uint64_t timestamp,
  size_t pub_index,
  size_t message_index)
{
  if (timestamps_to_messages_map_.count(timestamp) == 0) {
    timestamps_to_messages_map_[timestamp] = {};
  }
  timestamps_to_messages_map_[timestamp].push_back({pub_index, message_index});
}

size_t PlaybackNode::GetPublisherCount() const
{
  return generic_pubs_.size();
}

const std::vector<std::string>
PlaybackNode::GetRecordedTopicNames()
{
  std::vector<std::string> topic_names;
  for (const auto &[sub_index, sub_ptr] : subs_) {
    topic_names.push_back(sub_ptr->get_topic_name());
  }
  return topic_names;
}

}  // namespace ros2_benchmark

// Register as a component
#include "rclcpp_components/register_node_macro.hpp"
RCLCPP_COMPONENTS_REGISTER_NODE(ros2_benchmark::PlaybackNode)
