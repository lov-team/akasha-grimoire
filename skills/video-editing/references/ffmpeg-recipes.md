# FFmpeg 剪辑配方

所有路径替换为绝对路径，输出写入新文件；执行前确认目标不存在。

## 探测素材

```bash
ffprobe -v error \
  -show_entries format=duration,size,format_name:stream=codec_type,codec_name,width,height,avg_frame_rate,sample_rate,channels \
  -of json INPUT
```

## 生成低码率代理

```bash
ffmpeg -hide_banner -nostdin -i INPUT \
  -vf "scale=1280:-2:force_original_aspect_ratio=decrease" \
  -c:v libx264 -preset veryfast -crf 28 -c:a aac -b:a 128k -movflags +faststart PROXY.mp4
```

代理只用于编辑判断；最终渲染重新引用原始素材。

## 静态图片转镜头

```bash
ffmpeg -hide_banner -nostdin -loop 1 -i IMAGE \
  -t DURATION -vf "scale=WIDTH:HEIGHT:force_original_aspect_ratio=decrease,pad=WIDTH:HEIGHT:(ow-iw)/2:(oh-ih)/2:color=black,fps=FPS,format=yuv420p" \
  -an -c:v libx264 -crf 18 -movflags +faststart STILL_CLIP.mp4
```

需要慢推拉时在统一画幅后使用 `zoompan`，先渲染单镜头并检查边缘、抖动和实际帧数。

## 烧录字幕

```bash
ffmpeg -hide_banner -nostdin -i VIDEO \
  -vf "subtitles=CAPTIONS.srt" \
  -c:v libx264 -crf 18 -preset medium -c:a copy SUBTITLED.mp4
```

含空格、冒号或反斜杠的字幕路径优先从字幕所在目录执行，或使用正确的 FFmpeg filter 转义；不要用 shell 引号猜测成功。

## 旁白与音乐混音

```bash
ffmpeg -hide_banner -nostdin \
  -i VIDEO -i VOICE.wav -i MUSIC.wav \
  -filter_complex "[1:a]aresample=48000,volume=1.0[voice];[2:a]aresample=48000,volume=0.18[music];[voice][music]amix=inputs=2:duration=longest:normalize=0[mix]" \
  -map 0:v:0 -map "[mix]" -c:v copy -c:a aac -b:a 192k -shortest MIXED.mp4
```

默认使用固定电平混合：先把旁白和音乐分别调到目标响度，再直接 `amix`。不要让音乐音量由“是否正在说话”自动控制。只有 brief 明确要求 ducking 且试听确认没有抽吸感时，才加入轻微侧链；此时旁白必须先 `asplit` 为主混音与侧链检测两个显式分支。

交付前必须验证三件事：独立旁白轨可转写、独立音乐轨具有可测响度、最终混音仍能转写出旁白。程序化噪声、雨声和环境底噪属于 SFX/ambience，不能作为“音乐轨存在”的证据。

固定电平项目若两遍 `loudnorm` 报告 `Normalization Type: Dynamic`，不要把该结果当作最终母带。改用满足 true peak 上限的固定总增益，避免总线处理再次产生随对白变化的泵动。

## 两遍响度归一化

第一遍测量：

```bash
ffmpeg -hide_banner -i INPUT -af "loudnorm=I=-16:LRA=11:TP=-1.5:print_format=json" -f null -
```

第二遍把测量 JSON 中的 `input_i`、`input_lra`、`input_tp`、`input_thresh` 和 `target_offset` 写入 `measured_*` 参数，再输出新文件。不要省略第一遍后声称完成两遍归一化。
