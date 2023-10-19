// SPDX-FileCopyrightText: NVIDIA CORPORATION & AFFILIATES
// Copyright (c) 2023 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.
//
// SPDX-License-Identifier: Apache-2.0

#ifndef ROS2_BENCHMARK__DATA_LOADER_NODE_HPP_
#define ROS2_BENCHMARK__DATA_LOADER_NODE_HPP_

#include <filesystem>
#include <memory>
#include <string>
#include <unordered_map>
#include <vector>

#include "common.hpp"

#include "rclcpp/rclcpp.hpp"
#include "rclcpp/serialization.hpp"

#include "rosbag2_compression_zstd/zstd_decompressor.hpp"
#include "rosbag2_cpp/typesupport_helpers.hpp"
#include "rosbag2_cpp/readers/sequential_reader.hpp"
#include "rosbag2_cpp/storage_options.hpp"
#include "rosbag2_cpp/converter_options.hpp"

#include "std_msgs/msg/header.hpp"

#include "ros2_benchmark_interfaces/srv/set_data.hpp"
#include "ros2_benchmark_interfaces/srv/start_loading.hpp"
#include "ros2_benchmark_interfaces/srv/stop_loading.hpp"
#include "ros2_benchmark_interfaces/srv/get_topic_message_timestamps.hpp"

namespace ros2_benchmark
{

/// A data loader node for loading messages from a rosbag.
class DataLoaderNode : public rclcpp::Node
{
public:
  /// Construct a new DataLoaderNode object.
  explicit DataLoaderNode(const rclcpp::NodeOptions &);

  /// Destroy this node.
  ~DataLoaderNode();

private:
  /// Callback function for handling the set_data service.
  void SetDataServiceCallback(
    const ros2_benchmark_interfaces::srv::SetData::Request::SharedPtr request,
    ros2_benchmark_interfaces::srv::SetData::Response::SharedPtr response);

  /// Callback function for handling the start_loading service.
  void StartLoadingServiceCallback(
    const ros2_benchmark_interfaces::srv::StartLoading::Request::SharedPtr request,
    ros2_benchmark_interfaces::srv::StartLoading::Response::SharedPtr response);

  /// Callback function for handling the stop_loading service.
  void StopLoadingServiceCallback(
    const ros2_benchmark_interfaces::srv::StopLoading::Request::SharedPtr,
    ros2_benchmark_interfaces::srv::StopLoading::Response::SharedPtr);

  /// Callback function for handling the get_topic_message_timestamps service.
  void GetTopicMessageTimestampsSereviceCallback(
    const ros2_benchmark_interfaces::srv::GetTopicMessageTimestamps::Request::SharedPtr request,
    ros2_benchmark_interfaces::srv::GetTopicMessageTimestamps::Response::SharedPtr response);

  /// Create a TopicMessageTimestampArray message from the loaded message timeline.
  std::vector<ros2_benchmark_interfaces::msg::TopicMessageTimestampArray>
  CreateTopicMessageTimestampArrayMessageList(
    const int64_t start_time_ns,
    const int64_t end_time_ns);

  /// Use rosbag_reader_ to open the rosbag file located in the path rosbag_path_.
  void OpenRosbagFile();

  /// Publish the given serialized rosbag message with the specified publisher
  void PublishMessage(
    std::shared_ptr<rclcpp::GenericPublisher> publisher,
    std::shared_ptr<rosbag2_storage::SerializedBagMessage> message);

  /// Callback group for services.
  const rclcpp::CallbackGroup::SharedPtr service_callback_group_;

  /// A service object for SetData.
  const rclcpp::Service<ros2_benchmark_interfaces::srv::SetData>::SharedPtr
    set_data_service_;

  /// A service object for StartLoading.
  const rclcpp::Service<ros2_benchmark_interfaces::srv::StartLoading>::SharedPtr
    start_loading_service_;

  /// A service object for StopLoading.
  const rclcpp::Service<ros2_benchmark_interfaces::srv::StopLoading>::SharedPtr
    stop_loading_service_;

  /// A service object for GetTopicMessageTimestamps.
  const rclcpp::Service<ros2_benchmark_interfaces::srv::GetTopicMessageTimestamps>::SharedPtr
    get_topic_message_timestamps_service_;

  /// The path of the rosbag to be loaded.
  std::string rosbag_path_{""};

  /// The earlies timestamp observed in the loaded rosbag.
  int64_t first_timestamp_ns_{0};

  /// The latest timestamp observed in the loaded rosbag.
  int64_t last_timestamp_ns_{0};

  /// Timeline (rosbag-recorded timestamps) of the messages loaded from the rosbag.
  std::unordered_map<std::string, std::vector<int64_t>> topic_message_timestamps_;

  /// The publisher rate for publishing messages loaded from rosbag.
  /// It is ignored when requested to publish messages in real-time via the
  /// StartLoading service request (the publish_in_real_time field).
  int64_t publisher_period_ms_;

  /// Counter for tracking the number of messages being published.
  uint64_t played_message_count_{0};

  bool stop_playing_{false};
  std::mutex stop_playing_mutex_;

  /// A rosbag reader.
  rosbag2_cpp::readers::SequentialReader rosbag_reader_;

  /// A zstd message decompressor.
  rosbag2_compression_zstd::ZstdDecompressor decompressor_;

  /// Whether messages in the loaded rosbag are zstd-message-compressed.
  bool is_rosbag_compressed_{false};

  /// Generic publishers for all topics available from the loaded rosbag.
  std::unordered_map<std::string, std::shared_ptr<rclcpp::GenericPublisher>> publishers_;

  /// Dedicated publishers for TF messages
  std::unordered_map<std::string, std::shared_ptr<rclcpp::GenericPublisher>> tf_publishers_;
};

}  // namespace ros2_benchmark

#endif  // ROS2_BENCHMARK__DATA_LOADER_NODE_HPP_
