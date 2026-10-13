# 完整 RAW 拍摄、写卡与拍后恢复

[English](capture.md) · [测试记录](testing.md)

本次更新提供一条完整的 Z9 C5.32 原生流程：选择已验证的 RAW 配置，半按、全按、
释放快门，由固件把 NEF 写入虚拟卡，等待新的取景帧，再进入并返回两次 PHOTO 菜单。
菜单与文件由用户提供的固件生成；宿主没有拼一个替代 NEF，也没有自行绘制相机界面。

## 运行

按首页安装构建依赖，新增的 `libjpeg-dev` 用于功能性 JPEG 编码，`exfatprogs`
用于创建和只读检查虚拟卡。先退出原网页取景进程，再运行：

```sh
python -m pip install -r requirements-capture.txt
python tools/build.py --work-dir "$HOME/wonderlantern-z9-build" --jobs 2
python tools/make_cmos.py --width 8256 --height 5504 --bits 14 \
    --output .local/z9-14bit.raw
python tools/capture.py --firmware /绝对路径/z9-main-payload.bin \
    --output "$HOME/wonderlantern-z9-runs/capture-001" --audit
```

需要自己的场景时，给 `make_cmos.py` 加 `--image /路径/照片.jpg`。
处理包括重采样、移除 sRGB 曲线、RGGB 采样和拉伸到 0..16383。
输入为 32 字节头部加小端 u16 样本，共 **90,882,080 字节**；它不是打包 RAW14。
传入硬件模型后才按所选功能性路径打包。浮点中间数据限制为 32 行，全尺寸仍需数百 MB 内存，
应在启动 QEMU 前生成。640×480、12 位只是旧取景测试输入，不代表真实 CMOS 接口。

输出目录必须不存在，建议放在 Linux/ext4 文件系统。每轮建立新的 **8 GiB 稀疏卡**，
不会格式化真实设备或已有镜像；逻辑大小与实际占用不同，拍摄和派生校验卷会增加占用。
完整流程通常需数分钟，默认 `--seconds 600` 是启动后宿主期限；按键间隔与设备事件
使用 QEMU 虚拟时间。向该轮输出目录创建 `stop.request` 可请求停止自己的进程，
中断证据保留，不能计入通过。

网页仍提供取景与菜单按钮，完整拍摄通过上述独立命令执行。
`tools/capture-profile.json` 保存可复用配置。它通过原 QUAL/拨轮和菜单路径选择 RAW，
然后才释放快门。拍后菜单的前置条件是 RAW 与三路 JPEG 工作均确认完成，并且出现
新的可见取景帧；曝光中打开的菜单不算“拍后菜单恢复”。最后一次返回还需新产帧。

## 输出和验收

| 文件 | 含义 |
| --- | --- |
| `result.json` | 固件、构建、输入指纹，原生按键消费、设备确认、产帧和两轮拍后菜单记录 |
| `capture-card.raw` | guest 实际经 NVMe 写出的卡扇区 |
| `capture-card.audit.json`、目录清单 | 只读文件系统检查、源卡未改及完整文件条目 |
| `DSC_0001.NEF`、提取收据 | 从实际虚拟卡读取出的原文件，不替换内容 |
| `native-nef-audit.json` | `--audit` 执行 LibRaw 全样本解码比较及三路 JPEG 逐字节校验 |
| 截图、RAM 和编码快照 | 仅保存在本地，可能含固件派生数据，不能提交到公开仓库 |

NEF RAW 是 **8280×5520、14 位**，共 **45,705,600 个样本**；主 JPEG 预览为
**8256×5504**，中预览 **1620×1080**，缩略图 **160×120**。RAW、预览和 LCD
是三个不同接口的尺寸，不应混为一谈。已验收的宿主源为 **8256×5504**，硬件模型
按 RGGB 单元重采样到固件请求的 **8280×5520**；也可提供后者尺寸的输入，但不能
把它等同于真实传感器的边界像素。审计比较对象是实际 guest RAW 生产缓冲，
因此证明的是文件链路完整性，不等于已经验证传感器与原厂成像算法。

未加 `--audit` 时仍会提取 NEF，但没有通过独立全图验收。退出后可单独执行：

```sh
python tools/export_card.py --output /路径/capture-001
python tools/audit_native_nef.py --output /路径/capture-001
```

再次校验用 `--audit-name another-audit` 保留旧收据。看到文件名、收到按键或工具退出
成功，都不能单独当作完整相机验收。

## 实现与尚未实现

复用的功能模块包括有界完整帧 DMA、14 位打包、原地中性处理、通用 NV16 转换、
预览/缩略图重采样、libjpeg 编码、PCIe 地址窗口、NVMe 和中断 mask/pending/W1C。
数据处理完成后才产生完成通知。CCOMP 按请求回复及请求/反馈 GPIO 握手使原拍摄
控制器收尾；源停止、重新填充和第二路独立时序使取景恢复。没有改 PC、固件指令、
OS 等待结果或任务就绪标志。硬件断点仍用于只读观察和不完整外部 MCU/GPIO 的协调。

NEF 元数据与文件结构由固件写出。当前 RAW 实现是功能性的 14 位打包传递；
Compression=34713 标签及 LibRaw 能解码，不代表已实现尼康无损或高效率压缩。
降噪采用中性恒等处理，采样、统计、JPEG 参数和时序也尚非已确认的工厂算法。

**视频开始/停止、可播放录制文件、RAW 预拍摄、连拍稳定性、物理快门、AE/AF/PDAF
和真实 CMOS 编程均未验收。** LCD 的 video 计数只是取景，REC 按键被消费不代表
录制成功。RawRecord/预拍摄材料属于后续研究线索，不是本次已实现的新功能。

共享代码里的 ZR 源/ISP 完成实验默认关闭，不在 Z9 验收配置中；本仓库仅支持指定
Z9 固件。Z7 保持现状。新机型可复用设备与验收框架，但地址、位图、IRQ、布局和
完整生命周期必须按自己的固件验证。

当前 shared136 开发快照增加 `--profile lossless14 --audit`：两次释放快门的整轮照片／菜单恢复与每张 NEF 全像素独立审计。默认 compatibility 配置保持此前传输验证范围，不等于 F0 压缩算法验收。详见 [英文更新](capture.md) 和 [当前快照限制](development-snapshot.md)。
