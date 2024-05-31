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

#ifndef ROS2_BENCHMARK__PLAYBACK_NODE_HPP_
#define ROS2_BENCHMARK__PLAYBACK_NODE_HPP_

#include <map>
#include <memory>
#include <optional>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>

#include "common.hpp"

#include "rclcpp/rclcpp.hpp"
#include "rclcpp/serialization.hpp"

#include "ros2_benchmark_interfaces/srv/play_messages.hpp"
#include "ros2_benchmark_interfaces/srv/start_recording.hpp"
#include "ros2_benchmark_interfaces/srv/stop_recording.hpp"

#include "std_msgs/msg/header.hpp"

namespace ros2_benchmark
{

using TimePt = std::chrono::time_point<std::chrono::system_clock>;
using KeyTimePtMap = std::map<int32_t, TimePt>;

class PlaybackNode : public rclcpp::Node
{
public:
  /// Construct a new PlaybackNode object.
  explicit PlaybackNode(const rclcpp::NodeOptions &);

  /// Construct a new PlaybackNode object with a custom node name.
  explicit PlaybackNode(const std::string &, const rclcpp::NodeOptions &);

protected:
  /// Create a pair of publisher and subscriber for the given data format.
  void CreateGenericPubSub(const std::string data_format, const size_t index);

  /// Check if all the expected number of messages are buffered.
  virtual bool AreBuffersFull() const;

  /// Clear all the message buffers.
  virtual void ClearBuffers();

  /// Publish a message with the given index from each of the publishers.
  void PublishGroupMessages(
    size_t index,
    const std_msgs::msg::Header & header);

  /// Publish a buffered message from the selected publisher with revised a timestamp.
  virtual bool PublishMessage(
    const size_t pub_index,
    const size_t message_index,
    const std::optional<std_msgs::msg::Header> & header);

  /// Callback function for handling the start_recording service.
  void StartRecordingServiceCallback(
    const ros2_benchmark_interfaces::srv::StartRecording::Request::SharedPtr request,
    ros2_benchmark_interfaces::srv::StartRecording::Response::SharedPtr response);

  /// Callback function for handling the stop_recording service.
  void StopRecordingServiceCallback(
    const ros2_benchmark_interfaces::srv::StopRecording::Request::SharedPtr,
    ros2_benchmark_interfaces::srv::StopRecording::Response::SharedPtr);

  /// Callback function for handling the play_messages service.
  void PlayMessagesServiceCallback(
    const ros2_benchmark_interfaces::srv::PlayMessages::Request::SharedPtr request,
    ros2_benchmark_interfaces::srv::PlayMessages::Response::SharedPtr response);

  /// A subscriber callback function for recording the received messages.
  void GenericTypeRecordingSubscriberCallback(
    std::shared_ptr<rclcpp::SerializedMessage> serialized_message_ptr,
    size_t buffer_index);

  /// Publish the buffered messages in a timeline playback mode.
  void PlayMessagesTimelinePlayback(
    const ros2_benchmark_interfaces::srv::PlayMessages::Request::SharedPtr request,
    ros2_benchmark_interfaces::srv::PlayMessages::Response::SharedPtr response);

  /// Publish the buffered messages in a looping/sweeeping playback mode.
  void PlayMessagesLoopingSweeping(
    const ros2_benchmark_interfaces::srv::PlayMessages::Request::SharedPtr request,
    ros2_benchmark_interfaces::srv::PlayMessages::Response::SharedPtr response);

  /// Record a timestamp for a specified message key.
  bool RecordStartTimestamp(const int64_t & message_key);

  /// Add a message timestamp for a topic in timestamps_to_messages_map_.
  void AddToTimestampsToMessagesMap(
    uint64_t timestamp,
    size_t pub_index,
    size_t message_index);

  /// Get the count of all the recorded messages.
  virtual uint64_t GetRecordedMessageCount() const;

  /// Get the count of the recorded messages for the specified pub/sub index.
  virtual uint64_t GetRecordedMessageCount(size_t pub_index) const;

  /// Get the number of publishers created in this node.
  virtual size_t GetPublisherCount() const;

  /// Get all the topic names recorded from this node.
  const std::vector<std::string> GetRecordedTopicNames();

  /// Get the total number of timestamps stored in the message timeline variable.
  uint64_t GetTimestampsToMessagesCount() const;

  /// Callback group for services.
  const rclcpp::CallbackGroup::SharedPtr service_callback_group_;

  /// A service object for StartRecording.
  const rclcpp::Service<ros2_benchmark_interfaces::srv::StartRecording>::SharedPtr
    start_recording_service_;

  /// A service object for StopRecording.
  const rclcpp::Service<ros2_benchmark_interfaces::srv::StopRecording>::SharedPtr
    stop_recording_service_;

  /// A service object for PlayMessages.
  const rclcpp::Service<ros2_benchmark_interfaces::srv::PlayMessages>::SharedPtr
    play_messages_service_;

  /// Counter for tracking the number of messages published to produce unique keys.
  int message_counter_{0};

  std::mutex stop_recording_mutex_;
  std::mutex buffers_mutex_;
  bool stop_recording_;

  /// The number of messages that need to be buffered on each topic set from a
  /// StartRecording service request. All incoming messages are buffered if set to 0.
  size_t requested_buffer_length_;

  /// The maximum number of messages can be buffered in this node for each topic.
  /// It has higher condition priority than th length set in requested_buffer_length_.
  const size_t max_size_;

  /// A list for storing timestamps when messags are publishd.
  KeyTimePtMap start_timestamps_{};

  /// Treat the header.stamp.sec field in a message as a message ID.
  bool revise_timestamps_as_message_ids_{false};

  /// Data formats of the messages received and published by this node.
  std::vector<std::string> data_formats_;

  /// A topic name translation for matching the topic names of a data loadr node.
  /// It must be provided via the node's parameter in order to enable the timeline
  /// playback mode to store message timeline information provided from a data
  /// loader node correctly when there is one or more nodes present in between the
  /// data loader node and the current node. The index in this list matches the index
  /// of the pubs/subs created in this node.
  std::vector<std::string> timeline_topic_name_translations_;

  /// Buffers for storing serialized message pointers (of any ROS message types).
  std::unordered_map<size_t, std::vector<std::shared_ptr<rclcpp::SerializedMessage>>>
  serialized_msg_buffers_{};

  /// Subscribers for buffering incoming messages.
  std::unordered_map<size_t, std::shared_ptr<rclcpp::SubscriptionBase>> subs_;

  /// Generic publishers that publish the buffered serialized messages.
  std::unordered_map<size_t, std::shared_ptr<rclcpp::GenericPublisher>> generic_pubs_;

  /// Publisher/message indeices with ordered timestamps as keys.
  /// The value is a list of publisher/message index pairs.
  std::map<uint64_t, std::vector<std::pair<size_t, size_t>>> timestamps_to_messages_map_;

  /// Whether to enable timeline recording in the start_recording service
  bool record_data_timeline_{false};
};

}  // namespace ros2_benchmark

#endif  // ROS2_BENCHMARK__PLAYBACK_NODE_HPP_
