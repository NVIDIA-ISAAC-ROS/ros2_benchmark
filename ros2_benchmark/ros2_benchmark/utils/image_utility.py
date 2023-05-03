# SPDX-FileCopyrightText: NVIDIA CORPORATION & AFFILIATES
# Copyright (c) 2023 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# SPDX-License-Identifier: Apache-2.0


class Resolution:
    """Generic resolution value holder."""

    def __init__(self, width, height, name=''):
        """Initialize the resolution."""
        self._dict = {}
        self._dict['width'] = int(width)
        self._dict['height'] = int(height)
        self._dict['name'] = name

    def __str__(self) -> str:
        out_str = f'({self["width"]},{self["height"]})'
        if self['name']:
            out_str = f'{self["name"]} {out_str}'
        return out_str

    def __setitem__(self, key, value):
        self._dict[key] = value

    def __getitem__(self, key):
        return self._dict[key]

    def __repr__(self):
        return f'Resolution({self["width"]}, {self["height"]}, {self["name"]})'

    def yaml_representer(dumper, data):
        """Support dumping a Resolution object in YAML."""
        return dumper.represent_scalar('tag:yaml.org,2002:str', repr(data))


class ImageResolution:
    """Common image resolutions."""

    QUARTER_HD = Resolution(960, 540, 'Quarter HD')
    VGA = Resolution(640, 480, 'VGA')
    WVGA = Resolution(720, 480, 'WVGA')
    HD = Resolution(1280, 720, 'HD')
    FULL_HD = Resolution(1920, 1080, 'Full HD')
    FOUR_K = Resolution(3840, 2160, '4K')
