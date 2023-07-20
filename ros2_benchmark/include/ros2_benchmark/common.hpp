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

#ifndef ROS2_BENCHMARK__COMMON_HPP_
#define ROS2_BENCHMARK__COMMON_HPP_

#include <optional>

#include "rclcpp/rclcpp.hpp"

namespace ros2_benchmark
{

/// Quality-of-Service policy that will drop any messages due to queue size
/// ROS 2 intraprocess communications is only compatible with keep_last policy
const rclcpp::QoS kQoS{{RMW_QOS_POLICY_HISTORY_KEEP_LAST, 1000}};

/// Quality-of-Service policy that will not drop any messages
const rclcpp::QoS kBufferQoS{
  {RMW_QOS_POLICY_HISTORY_KEEP_LAST, 1000}, rmw_qos_profile_parameters};

const int kThreadDelay{50};

std::optional<rclcpp::QoS> getTopicQos(rclcpp::Node * node, const std::string & topic)
{
  /**
   * Given a topic name, get the QoS profile with which it is being published.
   * @param node pointer to the ROS node
   * @param topic name of the topic
   * @returns QoS profile of the publisher to the topic. If there are several publishers, it returns
   *     returns the profile of the first one on the list. If no publishers exist, it returns
   *     an empty value (optional).
   */
  std::string topic_resolved = node->get_node_base_interface()->resolve_topic_or_service_name(
    topic, false);
  auto topics_info = node->get_publishers_info_by_topic(topic_resolved);
  if (topics_info.size()) {
    auto profile = topics_info[0].qos_profile().get_rmw_qos_profile();
    return rclcpp::QoS{{RMW_QOS_POLICY_HISTORY_KEEP_LAST, 1000}, profile};
  }
  return {};
}

}  // namespace ros2_benchmark

#endif  // ROS2_BENCHMARK__COMMON_HPP_
