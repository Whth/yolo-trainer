import cv2
import click
import os
import zipfile
import datetime
import time
from pathlib import Path
import tempfile
import gradio as gr
import socket
import threading


class WebcamApp:
    def __init__(self, camera_source=0):
        self.camera_source = camera_source
        self.screenshots_dir = "screenshots"
        self.zip_dir = "zip_archives"
        Path(self.screenshots_dir).mkdir(exist_ok=True)
        Path(self.zip_dir).mkdir(exist_ok=True)
        
        # 用于视频流的多线程控制
        self.latest_frame = None
        self.running = False
        self.frame_lock = threading.Lock()
        self.video_thread = None

    def start_video_stream(self):
        """启动视频流线程"""
        if self.video_thread is None or not self.video_thread.is_alive():
            self.running = True
            self.video_thread = threading.Thread(
                target=self.video_reader, 
                args=(self.camera_source,),
                daemon=True
            )
            self.video_thread.start()

    def stop_video_stream(self):
        """停止视频流"""
        self.running = False
        if self.video_thread and self.video_thread.is_alive():
            self.video_thread.join()

    def video_reader(self, url):
        """持续读取视频流的线程函数"""
        cap = cv2.VideoCapture(url)

        if not cap.isOpened():
            print("无法打开视频流")
            return

        while self.running:
            ret, frame = cap.read()
            if not ret:
                print("无法读取帧，尝试重新连接...")
                time.sleep(1)
                cap.release()
                cap = cv2.VideoCapture(url)
                continue

            with self.frame_lock:
                self.latest_frame = frame.copy()

            # 控制帧率（可选）
            time.sleep(0.03)  # 约 30 FPS

        cap.release()

    def capture_frame(self):
        """捕获一帧图像"""
        if not self.running:
            self.start_video_stream()
            
        # 等待直到获取到帧或超时
        timeout = time.time() + 5  # 5秒超时
        while self.latest_frame is None and time.time() < timeout:
            time.sleep(0.1)
            
        if self.latest_frame is not None:
            # 转换BGR到RGB (OpenCV使用BGR，但Gradio需要RGB)
            frame_rgb = cv2.cvtColor(self.latest_frame, cv2.COLOR_BGR2RGB)
            return frame_rgb
        return None

    def get_screenshots_list(self):
        """获取已保存的截图列表"""
        screenshots = list(Path(self.screenshots_dir).glob("*.jpg"))
        screenshots.sort(key=lambda x: x.stat().st_mtime, reverse=True)

        if not screenshots:
            return "暂无截图"

        screenshot_info = []
        for screenshot in screenshots:
            stat = screenshot.stat()
            size = stat.st_size
            mtime = datetime.datetime.fromtimestamp(stat.st_mtime)
            size_str = (
                f"{size / 1024:.1f} KB"
                if size < 1024 * 1024
                else f"{size / (1024 * 1024):.1f} MB"
            )
            screenshot_info.append(
                f"📸 {screenshot.name} ({size_str}) - {mtime.strftime('%Y-%m-%d %H:%M:%S')}"
            )

        return "\n".join(screenshot_info)

    def get_zip_archives_list(self):
        """获取已创建的压缩包列表"""
        zip_files = list(Path(self.zip_dir).glob("*.zip"))
        zip_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)

        if not zip_files:
            return "暂无压缩包"

        zip_info = []
        for zip_file in zip_files:
            stat = zip_file.stat()
            size = stat.st_size
            mtime = datetime.datetime.fromtimestamp(stat.st_mtime)
            size_str = (
                f"{size / 1024:.1f} KB"
                if size < 1024 * 1024
                else f"{size / (1024 * 1024):.1f} MB"
            )
            zip_info.append(
                f"📦 {zip_file.name} ({size_str}) - {mtime.strftime('%Y-%m-%d %H:%M:%S')}"
            )

        return "\n".join(zip_info)

    def take_screenshot(self):
        """截图功能"""
        frame = self.capture_frame()
        if frame is not None:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"screenshot_{timestamp}.jpg"
            filepath = os.path.join(self.screenshots_dir, filename)

            # 保存图片 (需要转换回BGR)
            frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            cv2.imwrite(filepath, frame_bgr)

            return f"截图已保存: {filename}", frame
        return "截图失败", None

    def create_zip_download(self):
        """打包所有截图为zip文件"""
        screenshots = list(Path(self.screenshots_dir).glob("*.jpg"))

        if not screenshots:
            return None, "没有截图可下载", ""

        # 创建zip文件到本地目录
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        zip_filename = f"screenshots_{timestamp}.zip"
        zip_path = os.path.join(self.zip_dir, zip_filename)

        with zipfile.ZipFile(zip_path, "w") as zipf:
            for screenshot in screenshots:
                zipf.write(screenshot, screenshot.name)

        return (
            zip_path,
            f"已创建包含 {len(screenshots)} 张截图的压缩包",
            self.get_zip_archives_list(),
        )

    def create_all_zips_download(self):
        """创建包含所有压缩包的大压缩包"""
        zip_files = list(Path(self.zip_dir).glob("*.zip"))

        if not zip_files:
            return None, "没有压缩包可下载"

        # 创建临时文件包含所有压缩包
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        all_zips_filename = f"all_archives_{timestamp}.zip"
        all_zips_path = os.path.join(tempfile.gettempdir(), all_zips_filename)

        with zipfile.ZipFile(all_zips_path, "w") as zipf:
            for zip_file in zip_files:
                zipf.write(zip_file, zip_file.name)

        return all_zips_path, f"已创建包含 {len(zip_files)} 个压缩包的总打包文件"

    def clear_screenshots(self):
        """清理所有截图"""
        screenshots = list(Path(self.screenshots_dir).glob("*.jpg"))

        if not screenshots:
            return "没有截图需要清理"

        count = 0
        for screenshot in screenshots:
            try:
                screenshot.unlink()
                count += 1
            except Exception as e:
                print(f"删除文件 {screenshot} 失败: {e}")

        return f"已清理 {count} 张截图"

    def clear_zip_archives(self):
        """清理所有压缩包"""
        zip_files = list(Path(self.zip_dir).glob("*.zip"))

        if not zip_files:
            return "没有压缩包需要清理"

        count = 0
        for zip_file in zip_files:
            try:
                zip_file.unlink()
                count += 1
            except Exception as e:
                print(f"删除文件 {zip_file} 失败: {e}")

        return f"已清理 {count} 个压缩包"

    def cleanup(self):
        """清理资源"""
        self.stop_video_stream()


def get_local_ip():
    """获取本机局域网IP地址"""
    try:
        # 连接到一个外部地址来获取本机IP
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
        return local_ip
    except Exception:
        # 如果上述方法失败，尝试获取主机名对应的IP
        try:
            hostname = socket.gethostname()
            local_ip = socket.gethostbyname(hostname)
            return local_ip
        except Exception:
            return "127.0.0.1"


@click.command()
@click.help_option("-h", "--help")
@click.option(
    "--camera-source", "-c", default="0", help="摄像头设备索引或URL (默认: 0)"
)
@click.option("--port", "-p", default=7860, help="Gradio服务端口 (默认: 7860)")
@click.option("--host", "-s", default="0.0.0.0", help="服务主机地址 (默认: 0.0.0.0)")
def main(camera_source, port, host):
    """启动摄像头Web界面"""

    # 尝试将camera_source转换为整数，如果失败则保持为字符串（URL）
    try:
        camera_source = int(camera_source)
    except ValueError:
        # 保持为字符串，用于URL或其他非数字输入
        pass

    app = WebcamApp(camera_source)

    def refresh_camera():
        """刷新摄像头画面"""
        return app.capture_frame()

    def screenshot_handler():
        """处理截图"""
        message, frame = app.take_screenshot()
        screenshot_list = app.get_screenshots_list()
        return message, frame, screenshot_list

    def download_handler():
        """处理下载"""
        zip_path, message, zip_list = app.create_zip_download()
        return zip_path, message, zip_list

    def download_all_zips_handler():
        """处理下载所有压缩包"""
        zip_path, message = app.create_all_zips_download()
        return zip_path, message

    def clear_handler():
        """处理清理截图"""
        message = app.clear_screenshots()
        screenshot_list = app.get_screenshots_list()
        return message, screenshot_list

    def clear_zips_handler():
        """处理清理压缩包"""
        message = app.clear_zip_archives()
        zip_list = app.get_zip_archives_list()
        return message, zip_list

    def update_screenshots_list():
        """更新截图列表"""
        return app.get_screenshots_list()

    def update_zip_archives_list():
        """更新压缩包列表"""
        return app.get_zip_archives_list()

    # 创建Gradio界面
    with gr.Blocks(title="摄像头监控") as interface:
        gr.Markdown("# 摄像头实时监控")

        with gr.Row():
            with gr.Column():
                camera_output = gr.Image(label="摄像头画面", type="numpy")
                refresh_btn = gr.Button("刷新画面", variant="primary")

            with gr.Column():
                screenshot_btn = gr.Button("截图", variant="secondary")
                screenshot_msg = gr.Textbox(label="截图状态", interactive=False)

                download_btn = gr.Button("创建压缩包", variant="secondary")
                download_msg = gr.Textbox(label="压缩包状态", interactive=False)
                download_file = gr.File(label="下载文件")

                clear_btn = gr.Button("清理所有截图", variant="stop")
                clear_msg = gr.Textbox(label="清理状态", interactive=False)

        # 截图和压缩包列表区域
        with gr.Row():
            with gr.Column():
                gr.Markdown("## 已保存的截图")
                screenshot_list = gr.Textbox(
                    label="截图列表",
                    value=app.get_screenshots_list(),
                    interactive=False,
                    lines=8,
                    max_lines=15,
                )
                refresh_list_btn = gr.Button("刷新截图列表", variant="secondary")

            with gr.Column():
                gr.Markdown("## 压缩包管理")
                zip_archives_list = gr.Textbox(
                    label="压缩包列表",
                    value=app.get_zip_archives_list(),
                    interactive=False,
                    lines=8,
                    max_lines=15,
                )
                with gr.Row():
                    refresh_zip_btn = gr.Button("刷新压缩包列表", variant="secondary")
                    download_all_zips_btn = gr.Button(
                        "下载所有压缩包", variant="primary"
                    )

                download_all_msg = gr.Textbox(label="批量下载状态", interactive=False)
                download_all_file = gr.File(label="批量下载文件")

                clear_zips_btn = gr.Button("清理所有压缩包", variant="stop")
                clear_zips_msg = gr.Textbox(label="压缩包清理状态", interactive=False)

        # 绑定事件
        refresh_btn.click(fn=refresh_camera, outputs=[camera_output])
        screenshot_btn.click(
            fn=screenshot_handler,
            outputs=[screenshot_msg, camera_output, screenshot_list],
        )
        download_btn.click(
            fn=download_handler,
            outputs=[download_file, download_msg, zip_archives_list],
        )
        download_all_zips_btn.click(
            fn=download_all_zips_handler, outputs=[download_all_file, download_all_msg]
        )
        clear_btn.click(fn=clear_handler, outputs=[clear_msg, screenshot_list])
        clear_zips_btn.click(
            fn=clear_zips_handler, outputs=[clear_zips_msg, zip_archives_list]
        )
        refresh_list_btn.click(fn=update_screenshots_list, outputs=[screenshot_list])
        refresh_zip_btn.click(fn=update_zip_archives_list, outputs=[zip_archives_list])

        # 页面加载时自动刷新一次
        interface.load(fn=lambda: app.capture_frame(), outputs=[camera_output])

    try:
        print("启动摄像头Web界面...")
        print(f"摄像头设备: {camera_source}")

        # 获取本机IP地址
        local_ip = get_local_ip()

        print(f"访问地址: http://{host}:{port}")
        print(f"本机IP访问地址: http://{local_ip}:{port}")
        print(f"局域网内其他设备可通过以下地址访问: http://{local_ip}:{port}")

        interface.launch(server_name=host, server_port=port, share=False, debug=False)
    finally:
        app.cleanup()


if __name__ == "__main__":
    main()