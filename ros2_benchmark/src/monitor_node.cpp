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
}

rclcpp::QoS MonitorNode::ResolveTopicQoS(std::string topic_name,
                                        int num_attempts,
                                        int attempt_sleep_ms)
{
  std::optional<rclcpp::QoS> qos_opt;

  for (int i = 0; i < num_attempts; i++) {
    qos_opt = getTopicQos(this, topic_name);
    if (qos_opt.has_value()) break;
    std::this_thread::sleep_for(std::chrono::milliseconds(attempt_sleep_ms));
  }
  rclcpp::QoS qos = qos_opt.value_or(kQoS);

  RCLCPP_DEBUG(
    get_logger(),
    "[MonitorNode] Using QoS profile: history=%s, depth=%ld, reliability=%s, durability=%s",
    qos.get_rmw_qos_profile().history == RMW_QOS_POLICY_HISTORY_KEEP_LAST ? "KEEP_LAST" : "KEEP_ALL",
    qos.get_rmw_qos_profile().depth,
    qos.get_rmw_qos_profile().reliability == RMW_QOS_POLICY_RELIABILITY_RELIABLE ? "RELIABLE" : "BEST_EFFORT",
    qos.get_rmw_qos_profile().durability == RMW_QOS_POLICY_DURABILITY_TRANSIENT_LOCAL ? "TRANSIENT_LOCAL" : "VOLATILE");

  return qos;
}

void MonitorNode::CreateGenericTypeMonitorSubscriber()
{
  std::function<void(std::shared_ptr<rclcpp::SerializedMessage>)>
  monitor_subscriber_callback =
    std::bind(
    &MonitorNode::GenericMonitorSubscriberCallback,
    this,
    std::placeholders::_1);

  rclcpp::QoS qos = ResolveTopicQoS("output", 10, 100);

  monitor_sub_ = this->create_generic_subscription(
    "output",  // topic name
    monitor_data_format_,  // message type in the form of "package/type"
    qos,
    monitor_subscriber_callback);

  RCLCPP_INFO(
    get_logger(),
    "[MonitorNode] Created a generic type monitor subscriber: topic=\"%s\"",
    monitor_sub_->get_topic_name());
}

void MonitorNode::GenericMonitorSubscriberCallback(
  std::shared_ptr<rclcpp::SerializedMessage> serialized_message_ptr)
{
  if (revise_timestamps_as_message_ids_) {
    uint32_t end_timestamp = 0;
    uint8_t * byte_ptr = reinterpret_cast<uint8_t *>(&end_timestamp);
    *(byte_ptr + 0) = serialized_message_ptr->get_rcl_serialized_message().buffer[4];
    *(byte_ptr + 1) = serialized_message_ptr->get_rcl_serialized_message().buffer[5];
    *(byte_ptr + 2) = serialized_message_ptr->get_rcl_serialized_message().buffer[6];
    *(byte_ptr + 3) = serialized_message_ptr->get_rcl_serialized_message().buffer[7];
    // Here assumes the key is unique and identical to the second filed of timestamp
    RecordEndTimestamp(end_timestamp);
  } else {
    RecordEndTimestampAutoKey();
  }
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

  if (monitor_sub_ == nullptr) {
    // Create a monitor subscriber
    CreateGenericTypeMonitorSubscriber();
  }

  revise_timestamps_as_message_ids_ = request->revise_timestamps_as_message_ids;

  // Initialize message for return
  ros2_benchmark_interfaces::msg::TimestampedMessageArray timestamps{};

  // Record start time for timeout checking
  const auto start = std::chrono::system_clock::now();

  // Assume messages keys are unique (may receive stale timestamps)
  while ((end_timestamps_.size() < request->message_count) &&
    ((std::chrono::system_clock::now() - start) < std::chrono::seconds{request->timeout}))
  {
    std::this_thread::sleep_for(std::chrono::milliseconds(kThreadDelay));
  }

  // Record the keys of each message
  for (auto it : end_timestamps_) {
    timestamps.keys.emplace_back(it.first);
    timestamps.timestamps_ns.emplace_back(
      // Convert to nanoseconds
      std::chrono::duration_cast<std::chrono::nanoseconds>(
        it.second.time_since_epoch()).count());
  }

  response->timestamps = timestamps;

  end_timestamps_.clear();
}

}  // namespace ros2_benchmark

// Register as a component
#include "rclcpp_components/register_node_macro.hpp"
RCLCPP_COMPONENTS_REGISTER_NODE(ros2_benchmark::MonitorNode)
