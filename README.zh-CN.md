# WonderLantern ZR QEMU

[English / 完整构建与启动命令](README.md) · [当前成果、验证与限制](docs/development-snapshot.md) · [私有输入要求](docs/zr-inputs.md)

这是 QEMU10.2.4 上的 ZR C1.11 研究开发快照，复用 Z9 的共享 EXPEED7
设备模型 shared138。源码公开；尼康固件、解密后的私有代码、ROM 参数、
字体、图标、校准、SDK 和素材不公开，全部由用户在本地自行提供。

原始菜单、横屏 LCD、功能 Bayer 取景、全尺寸 RAW 传输和功能 lossless14
NEF 有本地整机研究证据。**H.265 10-bit 与 R3D 的完整相机录像仍未通过，
本版本不能宣传可录制可播放视频。** 原厂 ISP/DSP/H265/RAW 压缩/JPEG
算法也均未验收。XM6 文档的版本对应未确认，NeuPro 详细资料缺失，本地
神经网络复现 inconclusive。

默认横屏、英文；英文使用已明确记录的四字节缓存偏好修改，不冒充原始
NVM。视频模式半按对焦、全按开始、再次全按停止，快门不映射成 MOVIE 键。
升级包或 MAIN 固件本身目前不够：启动配置还需要用户自己的已验证参数
资源。使用 `tools/run_zr.py`，具体要求及哈希见英文 README 与输入文档。

photo 配置用于整轮照片/菜单恢复，main10 与 r3d 配置保留当前失败的录像
复现路径。设备单测与 START 回调不能替代文件、全量独立解码和拍后恢复。
这是按用户要求先公开的开发快照，正常录像验收仍要求两种格式都通过。
Z7 保持冻结；原 MagicLamp/ZR 输入目录未修改。

最新共享设备更新、状态查询契约与证据更正见 [shared138 notes](docs/shared138.md)。完整 H.265／R3D 录像与原机算法仍未验收。
