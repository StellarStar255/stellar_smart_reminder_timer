#!/usr/bin/env python3
"""测试通知和声音功能"""

import sys
import subprocess
import os

def test_sound():
    """测试声音播放"""
    print("测试声音播放...")
    sound_path = "/System/Library/Sounds/Glass.aiff"
    if os.path.exists(sound_path):
        # 播放3次模拟闹钟效果
        for i in range(3):
            subprocess.run(["afplay", sound_path], check=True)
        print("声音播放成功!")
        return True
    else:
        print("未找到系统声音文件")
        return False

def test_notification():
    """测试系统通知"""
    print("\n测试系统通知...")
    result = subprocess.run(
        ['osascript', '-e', 'display notification "这是一条测试通知" with title "星际脉动"'],
        capture_output=True,
        text=True
    )
    if result.returncode == 0:
        print("通知已发送!")
        print("请检查屏幕右上角或通知中心")
        return True
    else:
        print(f"通知发送失败: {result.stderr}")
        return False

def test_full_notification():
    """测试完整通知服务"""
    print("\n测试完整通知服务...")

    # Need PyQt6 for this
    try:
        from PyQt6.QtWidgets import QApplication
        sys.path.insert(0, '.')

        app = QApplication(sys.argv)

        from src.core.notification_service import NotificationService
        from src.models import Task

        service = NotificationService()

        # Create a mock completed task
        task = Task(
            id=1,
            name="测试任务",
            duration_seconds=60,
            category_id=1,
            elapsed_seconds=60
        )

        print("发送完成通知...")
        service.notify_task_completed(task)
        print("完整通知测试完成!")
        return True
    except Exception as e:
        print(f"完整测试失败: {e}")
        return False

if __name__ == "__main__":
    print("=" * 50)
    print("StellarPulse - 通知功能测试")
    print("=" * 50)

    test_sound()
    test_notification()

    print("\n" + "=" * 50)
    print("如果没有听到声音或看到通知，请检查:")
    print("1. 系统偏好设置 > 通知 > 确保脚本编辑器/终端有通知权限")
    print("2. 系统偏好设置 > 声音 > 确保音量不是静音")
    print("3. 勿扰模式是否开启")
    print("=" * 50)
