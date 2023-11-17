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

#include "ros2_benchmark/monitor_node.hpp"

namespace ros2_benchmark
{

MonitorNode::MonitorNode(
  const std::string & node_name,
  const rclcpp::NodeOptions & options)
: rclcpp::Node(node_name, options),
  monitor_index_((uint32_t)declare_parameter<uint16_t>("monitor_index", 0)),
  monitor_service_name_(kMonitorNodeServiceBaseName + std::to_string(monitor_index_)),
  monitor_data_format_(declare_parameter<std::string>("monitor_data_format", "")),
  service_callback_group_{create_callback_group(rclcpp::CallbackGroupType::MutuallyExclusive)},
  start_monitoring_service_{
    create_service<ros2_benchmark_interfaces::srv::StartMonitoring>(
      monitor_service_name_,
      std::bind(
        &MonitorNode::StartMonitoringServiceCallback,
        this,
        std::placeholders::_1,
        std::placeholders::_2),
      rmw_qos_profile_default,
      service_callback_group_)}
{
}

MonitorNode::MonitorNode(const rclcpp::NodeOptions & options)
: MonitorNode("MonitorNode", options)
{
  RCLCPP_INFO(
    get_logger(),
    "[MonitorNode] Starting a monitor node with a service name \"%s\"",
    monitor_service_name_.c_str());

  // Create a monitor subscriber
  CreateGenericTypeMonitorSubscriber();
}

void MonitorNode::CreateGenericTypeMonitorSubscriber()
{
  std::function<void(std::shared_ptr<rclcpp::SerializedMessage>)>
  monitor_subscriber_callback =
    std::bind(
    &MonitorNode::GenericMonitorSubscriberCallback,
    this,
    std::placeholders::_1);

  monitor_sub_ = this->create_generic_subscription(
    "output",                 // topic name
    monitor_data_format_,     // message type in the form of "package/type"
    kQoS,
    monitor_subscriber_callback);

  RCLCPP_INFO(
    get_logger(),
    "[MonitorNode] Created a generic type monitor subscriber: topic=\"%s\"",
    monitor_sub_->get_topic_name());
}

void MonitorNode::GenericMonitorSubscriberCallback(
  std::shared_ptr<rclcpp::SerializedMessage> serialized_message_ptr)
{
  std::lock_guard<std::mutex> lock(is_monitoring_mutex_);
  if (!is_monitoring_) {
    return;
  }

  uint32_t timestamp_key;
  if (revise_timestamps_as_message_ids_) {
    // Here assumes the key is unique and identical to the second filed of timestamp
    uint8_t * byte_ptr = reinterpret_cast<uint8_t *>(&timestamp_key);
    *(byte_ptr + 0) = serialized_message_ptr->get_rcl_serialized_message().buffer[4];
    *(byte_ptr + 1) = serialized_message_ptr->get_rcl_serialized_message().buffer[5];
    *(byte_ptr + 2) = serialized_message_ptr->get_rcl_serialized_message().buffer[6];
    *(byte_ptr + 3) = serialized_message_ptr->get_rcl_serialized_message().buffer[7];
  } else {
    // Use increamental numbers as timestamp keys
    timestamp_key = end_timestamps_.size();
  }

  RecordEndTimestamp(timestamp_key);
  if (record_start_timestamps_) {
    RecordStartTimestamp(
      timestamp_key,
      GetTimestampFromSerializedMessage(serialized_message_ptr));
  }
}

std::chrono::time_point<std::chrono::system_clock>
MonitorNode::GetTimestampFromSerializedMessage(
  std::shared_ptr<rclcpp::SerializedMessage> serialized_message_ptr)
{
  int32_t timestamp_sec;
  uint8_t * sec_byte_ptr = reinterpret_cast<uint8_t *>(&timestamp_sec);
  *(sec_byte_ptr + 0) = serialized_message_ptr->get_rcl_serialized_message().buffer[4];
  *(sec_byte_ptr + 1) = serialized_message_ptr->get_rcl_serialized_message().buffer[5];
  *(sec_byte_ptr + 2) = serialized_message_ptr->get_rcl_serialized_message().buffer[6];
  *(sec_byte_ptr + 3) = serialized_message_ptr->get_rcl_serialized_message().buffer[7];

  uint32_t timestamp_nanosec;
  uint8_t * ns_byte_ptr = reinterpret_cast<uint8_t *>(&timestamp_nanosec);
  *(ns_byte_ptr + 0) = serialized_message_ptr->get_rcl_serialized_message().buffer[8];
  *(ns_byte_ptr + 1) = serialized_message_ptr->get_rcl_serialized_message().buffer[9];
  *(ns_byte_ptr + 2) = serialized_message_ptr->get_rcl_serialized_message().buffer[10];
  *(ns_byte_ptr + 3) = serialized_message_ptr->get_rcl_serialized_message().buffer[11];

  RCLCPP_DEBUG(
    get_logger(),
    "[MonitorNode] timestamp_sec=%d, timestamp_nanosec=%d",
    timestamp_sec, timestamp_nanosec);

  std::chrono::time_point<std::chrono::system_clock> timestamp(
    std::chrono::seconds(timestamp_sec) + std::chrono::nanoseconds(timestamp_nanosec));
  return timestamp;
}

bool MonitorNode::RecordStartTimestamp(
  const int32_t & message_key,
  const std::chrono::time_point<std::chrono::system_clock> & timestamp)
{
  // If key already exists in start map, return false
  if (start_timestamps_.count(message_key) > 0) {
    RCLCPP_ERROR(
      get_logger(),
      "[MonitorNode] Message key %d existed when recording a start timestamp",
      message_key);
    return false;
  }

  RCLCPP_DEBUG(
    get_logger(),
    "[MonitorNode] Recorded a start timestamp for message key %d",
    message_key);

  // Add new entry to start timestamps
  start_timestamps_.emplace(message_key, timestamp);
  return true;
}

bool MonitorNode::RecordEndTimestamp(const int32_t & message_key)
{
  // Record timestamp first, in case we need to wait to acquire mutex
  const auto timestamp{std::chrono::system_clock::now()};

  // If key already exists in end map, return false
  if (end_timestamps_.count(message_key) > 0) {
    RCLCPP_ERROR(
      get_logger(),
      "[MonitorNode] Message key %d existed when recording an end timestamp",
      message_key);
    return false;
  }

  RCLCPP_DEBUG(
    get_logger(),
    "[MonitorNode] Recorded an end timestamp for message key %d",
    message_key);

  // Add new entry to end timestamps
  end_timestamps_.emplace(message_key, timestamp);
  return true;
}

bool MonitorNode::RecordEndTimestampAutoKey()
{
  return RecordEndTimestamp(end_timestamps_.size());
}

void MonitorNode::StartMonitoringServiceCallback(
  const ros2_benchmark_interfaces::srv::StartMonitoring::Request::SharedPtr request,
  ros2_benchmark_interfaces::srv::StartMonitoring::Response::SharedPtr response)
{
  RCLCPP_DEBUG(
    get_logger(),
    "[MonitorNode] Enter monitor node callback");

  {
    std::lock_guard<std::mutex> lock(is_monitoring_mutex_);
    revise_timestamps_as_message_ids_ = request->revise_timestamps_as_message_ids;
    record_start_timestamps_ = request->record_start_timestamps;
    is_monitoring_ = true;
  }

  // Initialize message for return
  ros2_benchmark_interfaces::msg::TimestampedMessageArray response_start_timestamps{};
  ros2_benchmark_interfaces::msg::TimestampedMessageArray response_end_timestamps{};

  // Record start time for timeout checking
  const auto start = std::chrono::system_clock::now();

  // Assume messages keys are unique (may receive stale timestamps)
  while ((request->message_count == 0 || end_timestamps_.size() < request->message_count) &&
    ((std::chrono::system_clock::now() - start) < std::chrono::seconds{request->timeout}))
  {
    std::this_thread::sleep_for(std::chrono::milliseconds(kThreadDelay));
  }

  {
    std::lock_guard<std::mutex> lock(is_monitoring_mutex_);
    is_monitoring_ = false;
  }

  // Record the keys of each message
  for (auto it : start_timestamps_) {
    response_start_timestamps.keys.emplace_back(it.first);
    response_start_timestamps.timestamps_ns.emplace_back(
      // Convert to nanoseconds
      std::chrono::duration_cast<std::chrono::nanoseconds>(
        it.second.time_since_epoch())
      .count());
  }
  for (auto it : end_timestamps_) {
    response_end_timestamps.keys.emplace_back(it.first);
    response_end_timestamps.timestamps_ns.emplace_back(
      // Convert to nanoseconds
      std::chrono::duration_cast<std::chrono::nanoseconds>(
        it.second.time_since_epoch())
      .count());
  }

  response->start_timestamps = response_start_timestamps;
  response->end_timestamps = response_end_timestamps;

  {
    std::lock_guard<std::mutex> lock(is_monitoring_mutex_);
    start_timestamps_.clear();
    end_timestamps_.clear();
  }
}

}  // namespace ros2_benchmark

// Register as a component
#include "rclcpp_components/register_node_macro.hpp"
RCLCPP_COMPONENTS_REGISTER_NODE(ros2_benchmark::MonitorNode)
