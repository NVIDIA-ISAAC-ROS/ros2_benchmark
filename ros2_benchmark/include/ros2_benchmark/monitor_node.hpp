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

#ifndef ROS2_BENCHMARK__MONITOR_NODE_HPP_
#define ROS2_BENCHMARK__MONITOR_NODE_HPP_

#include <map>
#include <memory>
#include <string>

#include "common.hpp"

#include "rclcpp/rclcpp.hpp"
#include "rclcpp/serialization.hpp"

#include "ros2_benchmark_interfaces/srv/start_monitoring.hpp"

namespace ros2_benchmark
{

using TimePt = std::chrono::time_point<std::chrono::system_clock>;
using KeyTimePtMap = std::map<int32_t, TimePt>;

constexpr char kMonitorNodeServiceBaseName[] = "start_monitoring";

class MonitorNode : public rclcpp::Node
{
public:
  /// Construct a new MonitorNode object.
  explicit MonitorNode(const rclcpp::NodeOptions &);

  /// Construct a new MonitorNode object with a custom node name.
  explicit MonitorNode(const std::string &, const rclcpp::NodeOptions &);

protected:
  /// Create a generic type monitor subscriber.
  void CreateGenericTypeMonitorSubscriber();

  /// A subscriber callback function for generic ROS type message monitor
  /// (that adds end timestamps).
  void GenericMonitorSubscriberCallback(
    std::shared_ptr<rclcpp::SerializedMessage> serialized_message_ptr);

  /// Callback function to start monitoring the incoming messages.
  void StartMonitoringServiceCallback(
    const ros2_benchmark_interfaces::srv::StartMonitoring::Request::SharedPtr,
    ros2_benchmark_interfaces::srv::StartMonitoring::Response::SharedPtr response);

  /// Record an end timestamp for a given message key.
  bool RecordEndTimestamp(const int32_t & message_key);

  /// Record an end timestamp with an automatic generated key.
  bool RecordEndTimestampAutoKey();

  /// Index of this monitor node.
  uint32_t monitor_index_;

  /// The name of the service StartMonitoring created in this nodee
  std::string monitor_service_name_;

  /// Data format of the monitor subscriber.
  std::string monitor_data_format_;

  /// Treat the header.stamp.sec field in a message as a message ID.
  bool revise_timestamps_as_message_ids_{false};

  /// A subscriber that monitors the incoming messages for a specified topic
  /// and record their arrival timestamps.
  std::shared_ptr<rclcpp::SubscriptionBase> monitor_sub_{nullptr};

  /// A list for storing timestamps of the observed messages.
  KeyTimePtMap end_timestamps_{};

  /// Callback group for services.
  const rclcpp::CallbackGroup::SharedPtr service_callback_group_;

  /// A service object for StartMonitoring.
  rclcpp::Service<ros2_benchmark_interfaces::srv::StartMonitoring>::SharedPtr
    start_monitoring_service_;
};

}  // namespace ros2_benchmark

#endif  // ROS2_BENCHMARK__MONITOR_NODE_HPP_
