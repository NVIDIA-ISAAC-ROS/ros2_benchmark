"""
Performance test for apriltag_ros.

The graph consists of the following:
- Preprocessors:
	1. PrepResizeNode: resizes images to HD
- Graph under Test:
	1. AprilTagNode: detects Apriltags

Required:
- Packages:
	- apriltag_ros
- Datasets:
	- assets/datasets/r2b_dataset/r2b_storage
"""

from launch_ros.actions import ComposableNodeContainer
from launch_ros.descriptions import ComposableNode
import launch
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration

from ros2_benchmark import ImageResolution
from ros2_benchmark import ROS2BenchmarkConfig, ROS2BenchmarkTest

IMAGE_RESOLUTION = ImageResolution.HD
ROSBAG_PATH = 'datasets/r2b_dataset/r2b_storage'


def launch_setup(container_prefix, container_sigterm_timeout):
    """Launch the DNN Image encoder, Triton node and UNet decoder node."""
    
    launch_args = [
    DeclareLaunchArgument(
        'network_image_width',
        default_value='1820',
        description='The input image width that the network expects'),
    DeclareLaunchArgument(
        'network_image_height',
        default_value='1024',
        description='The input image height that the network expects'),
    DeclareLaunchArgument(
        'encoder_image_mean',
        default_value='[0.5, 0.5, 0.5]',
        description='The mean for image normalization'),
    DeclareLaunchArgument(
        'encoder_image_stddev',
        default_value='[0.5, 0.5, 0.5]',
        description='The standard deviation for image normalization'),
    DeclareLaunchArgument(
        'model_name',
        default_value='citysemsegformer',
        description='The name of the model'),
    DeclareLaunchArgument(
        'model_repository_paths',
        default_value='["/workspaces/isaac_ros-dev/models/"]',
        description='The absolute path to the repository of models'),
    DeclareLaunchArgument(
        'max_batch_size',
        default_value='0',
        description='The maximum allowed batch size of the model'),
    DeclareLaunchArgument(
        'input_tensor_names',
        default_value='["input_tensor"]',
        description='A list of tensor names to bound to the specified input binding names'),
    DeclareLaunchArgument(
        'input_binding_names',
        default_value='["input"]',
        description='A list of input tensor binding names (specified by model)'),
    DeclareLaunchArgument(
        'input_tensor_formats',
        default_value='["nitros_tensor_list_nchw_rgb_f32"]',
        description='The nitros format of the input tensors'),
    DeclareLaunchArgument(
        'output_tensor_names',
        default_value='["output_tensor"]',
        description='A list of tensor names to bound to the specified output binding names'),
    DeclareLaunchArgument(
        'output_binding_names',
        default_value='["output"]',
        description='A  list of output tensor binding names (specified by model)'),
    DeclareLaunchArgument(
        'output_tensor_formats',
        default_value='["nitros_tensor_list_nhwc_rgb_f32"]',
        description='The nitros format of the output tensors'),
    DeclareLaunchArgument(
        'network_output_type',
        default_value='argmax',
        description='The output type that the network provides (softmax, sigmoid or argmax)'),
    DeclareLaunchArgument(
        'color_segmentation_mask_encoding',
        default_value='rgb8',
        description='The image encoding of the colored segmentation mask (rgb8 or bgr8)'),
    DeclareLaunchArgument(
        'mask_width',
        default_value='1820',
        description='The width of the segmentation mask'),
    DeclareLaunchArgument(
        'mask_height',
        default_value='1024',
        description='The height of the segmentation mask'),
    ]
    
    # DNN Image Encoder parameters
    network_image_width = LaunchConfiguration('network_image_width')
    network_image_height = LaunchConfiguration('network_image_height')
    encoder_image_mean = LaunchConfiguration('encoder_image_mean')
    encoder_image_stddev = LaunchConfiguration('encoder_image_stddev')
    
    # Triton parameters
    model_name = LaunchConfiguration('model_name')
    model_repository_paths = LaunchConfiguration('model_repository_paths')
    max_batch_size = LaunchConfiguration('max_batch_size')
    input_tensor_names = LaunchConfiguration('input_tensor_names')
    input_binding_names = LaunchConfiguration('input_binding_names')
    input_tensor_formats = LaunchConfiguration('input_tensor_formats')
    output_tensor_names = LaunchConfiguration('output_tensor_names')
    output_binding_names = LaunchConfiguration('output_binding_names')
    output_tensor_formats = LaunchConfiguration('output_tensor_formats')
    
    # U-Net Decoder parameters
    network_output_type = LaunchConfiguration('network_output_type')
    color_segmentation_mask_encoding = LaunchConfiguration('color_segmentation_mask_encoding')
    mask_width = LaunchConfiguration('mask_width')
    mask_height = LaunchConfiguration('mask_height')
    
    data_loader_node = ComposableNode(
        name='DataLoaderNode',
        namespace=TestImageSegmentationNode.generate_namespace(),
        package='ros2_benchmark',
        plugin='ros2_benchmark::DataLoaderNode',
        remappings=[
            ('hawk_0_left_rgb_image', 'data_loader/image'),
            ('hawk_0_left_rgb_camera_info', 'data_loader/camera_info')]
    )
    
    # Parameters preconfigured for PeopleSemSegNet.
    encoder_node = ComposableNode(
        name='dnn_image_encoder',
        namespace=TestImageSegmentationNode.generate_namespace(),
        package='isaac_ros_dnn_encoders',
        plugin='nvidia::isaac_ros::dnn_inference::DnnImageEncoderNode',
        parameters=[{
            'network_image_width': network_image_width,
            'network_image_height': network_image_height,
            'image_mean': encoder_image_mean,
            'image_stddev': encoder_image_stddev,
        }],
        remappings=[
            ('image', 'data_loader/image'),
            ('encoded_tensor', 'tensor_pub')
      ]
    )
    
    playback_node = ComposableNode(
        name='PlaybackNode',
        namespace=TestImageSegmentationNode.generate_namespace(),
        package='ros2_benchmark',
        plugin='ros2_benchmark::PlaybackNode',
        parameters=[{
    	  'data_formats': [
          'sensor_msgs/msg/Image',
    	],
        }],
        remappings=[
    	  ('buffer/input0', 'data_loader/image'),
    	  ('input0', 'image'),
      ]
    )
    
    triton_node = ComposableNode(
        name='triton_node',
        namespace=TestImageSegmentationNode.generate_namespace(),
        package='isaac_ros_triton',
        plugin='nvidia::isaac_ros::dnn_inference::TritonNode',
        parameters=[{
          'model_name': model_name,
    	  'model_repository_paths': model_repository_paths,
    	  'max_batch_size': max_batch_size,
    	  'input_tensor_names': input_tensor_names,
    	  'input_binding_names': input_binding_names,
    	  'input_tensor_formats': input_tensor_formats,
    	  'output_tensor_names': output_tensor_names,
    	  'output_binding_names': output_binding_names,
    	  'output_tensor_formats': output_tensor_formats,
        }],
    )
    
    unet_decoder_node = ComposableNode(
        name='unet_decoder_node',
        namespace=TestImageSegmentationNode.generate_namespace(),
        package='isaac_ros_unet',
        plugin='nvidia::isaac_ros::unet::UNetDecoderNode',
        parameters=[{
    	  'network_output_type': network_output_type,
    	  'color_segmentation_mask_encoding': color_segmentation_mask_encoding,
    	  'mask_width': mask_width,
    	  'mask_height': mask_height,
    	  'color_palette': [0x556B2F, 0x800000, 0x008080, 0x000080, 0x9ACD32, 0xFF0000, 0xFF8C00,
              0xFFD700, 0x00FF00, 0xBA55D3, 0x00FA9A, 0x00FFFF, 0x0000FF, 0xF08080,
              0xFF00FF, 0x1E90FF, 0xDDA0DD, 0xFF1493, 0x87CEFA, 0xFFDEAD],
        }],
    )
    
    monitor_node = ComposableNode(
        name='MonitorNode',
        namespace=TestImageSegmentationNode.generate_namespace(),
        package='ros2_benchmark',
        plugin='ros2_benchmark::MonitorNode',
        parameters=[{
            'monitor_data_format': 'sensor_msgs/msg/Image',
        }],
        remappings=[
            ('output', 'unet/colored_segmentation_mask')
        ]
    )
    
    composable_node_container = ComposableNodeContainer(
        name='container',
        namespace=TestImageSegmentationNode.generate_namespace(),
        package='rclcpp_components',
        executable='component_container_mt',
        prefix=container_prefix,
        sigterm_timeout=container_sigterm_timeout,
        composable_node_descriptions=[
    	  data_loader_node,
    	  encoder_node,
    	  playback_node,
    	  monitor_node,
    	  triton_node,
    	  unet_decoder_node
        ],
        output='screen'
    )
    
    
    final_launch_description = launch_args + [composable_node_container]
    return [launch.LaunchDescription(final_launch_description)]

def generate_test_description():
    return TestImageSegmentationNode.generate_test_description_with_nsys(launch_setup)

class TestImageSegmentationNode(ROS2BenchmarkTest):
    """Performance test for CitySegfirner."""
    
    # Custom configurations
    config = ROS2BenchmarkConfig(
        benchmark_name='image_segmentation_ros ImageSegmentationNode Benchmark',
        input_data_path=ROSBAG_PATH,
        # The slice of the rosbag to use
        # Upper and lower bounds of peak throughput search window
        publisher_upper_frequency=100.0,
        publisher_lower_frequency=10.0,
        # The number of frames to be buffered
        playback_message_buffer_size=300,
        start_recording_service_timeout_sec=60,
        start_recording_service_future_timeout_sec=60,
        custom_report_info={'data_resolution': IMAGE_RESOLUTION},
        benchmark_mode='TIMELINE',
	assets_root='/workspaces/isaac_ros-dev/src/ros2_benchmark/assets',
    )
    
    def test_benchmark(self):
        self.run_benchmark()
