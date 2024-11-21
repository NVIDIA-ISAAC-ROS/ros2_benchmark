# ros2_benchmark city_segoformer

## Overview

Measuring benchmark [CitySegformer](https://catalog.ngc.nvidia.com/orgs/nvidia/teams/tao/models/citysemsegformer) performance


## Quickstart

1. Set up your development environment by following the instructions [here](https://github.com/NVIDIA-ISAAC-ROS/isaac_ros_common/blob/main/docs/dev-env-setup.md).
2. Clone this repository and its dependencies under `~/workspaces/isaac_ros-dev/src`.

    ```bash
    cd ~/workspaces/isaac_ros-dev/src
    ```

    ```bash
    git clone https://github.com/NVIDIA-ISAAC-ROS/isaac_ros_common
    ```

    ```bash
    git clone https://github.com/NVIDIA-ISAAC-ROS/isaac_ros_nitros
    ```

    ```bash
    git clone https://github.com/NVIDIA-ISAAC-ROS/isaac_ros_image_segmentation
    ```

    ```bash
    git clone https://github.com/NVIDIA-ISAAC-ROS/isaac_ros_dnn_inference
    ```

    ```bash
    git clone https://github.com/NVIDIA-ISAAC-ROS/isaac_ros_image_pipeline
    ```
    
    ```bash
    git clone https://github.com/NVIDIA-ISAAC-ROS/ros2_benchmark
    ```

3. Pull down r2b dataset 2023 by following the instructions [here](https://github.com/SnowMasaya/ros2_benchmark#datasets) or fetch just the rosbag used in this Quickstart with the following command. 

    ```bash
    mkdir -p $R2B_WS_HOME/src/ros2_benchmark/assets/datasets/r2b_dataset/r2b_storage && \
    cd $R2B_WS_HOME/src/ros2_benchmark/assets/datasets/r2b_dataset/r2b_storage && \
      wget --content-disposition 'https://api.ngc.nvidia.com/v2/resources/nvidia/isaac/r2bdataset2023/versions/1/files/r2b_storage/metadata.yaml' && \
      wget --content-disposition 'https://api.ngc.nvidia.com/v2/resources/nvidia/isaac/r2bdataset2023/versions/1/files/r2b_storage/r2b_storage_0.db3'
    ```

4. Launch the Docker container using the `run_dev.sh` script:

    ```bash
    cd ~/workspaces/isaac_ros-dev/src/isaac_ros_common && \
      ./scripts/run_dev.sh
    ```

5. Download the `City Segoformer` ETLT file:

   [City Segformer](https://catalog.ngc.nvidia.com/orgs/nvidia/teams/tao/models/citysemsegformer)

    ```bash
    mkdir -p /workspaces/isaac_ros-dev/models/citysemsegformer/1
    cd /workspaces/isaac_ros-dev/models/citysemsegformer
    wget --content-disposition https://api.ngc.nvidia.com/v2/models/nvidia/tao/citysemsegformer/versions/deployable_v1.0/zip -O citysemsegformer_deployable_v1.0.zip
    unzip citysemsegformer_deployable_v1.0.zip

    ```

6. Convert the ETLT file to a TensorRT plan file:

    ```bash
    /opt/nvidia/tao/tao-converter -k tlt_encode -d 3,1024,1820  -p input,1x3x1024x1820,1x3x1024x1820,1x3x1024x1820 -t fp16 -e /workspaces/isaac_ros-dev/models/citysemsegformer/1/model.plan ./citysemsegformer.etlt
    ```

7. Create a file called `/workspaces/isaac_ros-dev/models/citysemsegformer/config.pbtxt` by copying the sample Triton config file:

    ```bash
    name: "citysemsegformer"
    platform: "tensorrt_plan"
    max_batch_size: 0
    input [
      {
    	name: "input"
    	data_type: TYPE_FP32
    	dims: [ 1, 3, 1024, 1820 ]
      }
    ]
    output [
      {
    	name: "output"
    	data_type: TYPE_INT32
    	dims: [ 1, 1024, 1820, 1 ]
      }
    ]
    version_policy: {
      specific {
    	versions: [ 1 ]
      }
    }
    
    ```

8. Inside the container, build and source the workspace:

    ```bash
    cd /workspaces/isaac_ros-dev && \
      colcon build --symlink-install && \
      source install/setup.bash
    ```

9. Run the following launch files to spin up a demo of this package:

    ```bash
    launch_test src/ros2_benchmark/scripts/city_segformer/image_segmentation_ros_node_city_segformer.py
    ```
Once the benchmark is finished, the final performance measurements are displayed in the terminal. Additionally, the final results and benchmark metadata (e.g., system information, benchmark configurations) are also exported as a JSON file.

