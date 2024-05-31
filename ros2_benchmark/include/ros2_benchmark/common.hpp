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

#ifndef ROS2_BENCHMARK__COMMON_HPP_
#define ROS2_BENCHMARK__COMMON_HPP_

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

}  // namespace ros2_benchmark

#endif  // ROS2_BENCHMARK__COMMON_HPP_
