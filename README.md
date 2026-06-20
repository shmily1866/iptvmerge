# AptvMerge (Docker Edition)

这是一个将不同流派的音视频直播源（例如只有视频的 m3u8 和只有音频的 m3u8）进行精准对齐和合并的高性能本地服务，专为解决直播延迟、音视频不同步等问题而生。

基于 AptvMerge 原版 v2.1 最新黑科技架构重构。

## 🌟 核心特性
- **Native 校准合流**：使用 FFmpeg 原生的 `-itsoffset` 和 `aresample=async=1` 异步重采样技术，从物理时间戳层面强行对齐音视频，彻底告别播放器卡顿、转圈和时间戳断层。
- **高容灾与容错**：采用原生 MPEG-TS 直供浏览器，结合 `4096` 级别的巨型数据包队列和 5秒极速断线重连机制，哪怕上游信号恶劣，合并端依然稳如磐石。
- **纯净单进程架构**：废除了笨重的多进程管道缓冲控制逻辑，单一 FFmpeg 进程解决所有战斗。
- **无痛跨平台部署**：完全基于轻量化 Docker 构建，支持一键在 OpenWrt、NAS、Linux 部署。

## 🚀 部署指南 (基于 Docker)

本服务提供预先构建的 Docker 镜像，只需一行命令即可部署。

### 1. 运行服务
如果您的设备安装了 Docker，可以直接运行以下命令：

```bash
docker run -d \
  --name iptvmerge \
  --restart unless-stopped \
  -p 38080:38080 \
  -v /root/iptvmerge/data:/app/data \
  ghcr.io/您的GitHub用户名/您的仓库名:latest
```

*注意：请将命令最后的 `ghcr.io/...` 替换为您自己在 GitHub Packages 中的实际镜像地址。所有的播放配置、历史记录将自动保存在宿主机的 `/root/iptvmerge/data` 目录中。*

### 2. 使用控制面板
容器启动后，在浏览器中访问您的服务器 IP 和绑定的端口：
```
http://<您的IP>:38080
```
即可看到带实时播放预览的可视化操作后台。

## 🛠️ 本地 Windows 开发测试
如果您想在 Windows 本地测试代码：
1. 请确保根目录有 `ffmpeg.exe`。
2. 双击运行 `start.bat`。

---
**致谢**
感谢原版 AptvMerge 作者的灵感与优秀的开源架构。
