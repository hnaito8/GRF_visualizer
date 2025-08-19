#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Arduino床反力データ リアルタイム可視化アプリ
管理者モードとユーザーモードの2つの画面を持つGUIアプリケーション
"""

import sys
import time
import threading
from collections import deque
from PyQt5.QtWidgets import (
    QApplication,
    QMainWindow,
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
    QPushButton,
    QLabel,
)
from PyQt5.QtCore import QTimer, pyqtSignal, QObject, Qt
from PyQt5.QtGui import QFont
import pyqtgraph as pg
import serial
import serial.tools.list_ports


class DataReceiver(QObject):
    """シリアル通信でデータを受信するクラス"""

    data_received = pyqtSignal(float, float)  # timestamp, force

    def __init__(self, port="/dev/cu.usbmodem14201", baudrate=9600):
        super().__init__()
        self.port = port
        self.baudrate = baudrate
        self.serial_conn = None
        self.running = False
        self.thread = None

    def start_receiving(self):
        """データ受信開始"""
        if self.running:
            return

        try:
            # シリアルポート接続
            self.serial_conn = serial.Serial(self.port, self.baudrate, timeout=1)
            self.running = True

            # 受信スレッド開始
            self.thread = threading.Thread(target=self._receive_data, daemon=True)
            self.thread.start()
            print(f"シリアル通信開始: {self.port} @ {self.baudrate}")

        except Exception as e:
            print(f"シリアルポート接続エラー: {e}")
            # エラー時はダミーデータで動作
            self.running = True
            self.thread = threading.Thread(target=self._dummy_data, daemon=True)
            self.thread.start()
            print("ダミーデータモードで動作中")

    def stop_receiving(self):
        """データ受信停止"""
        self.running = False
        if self.serial_conn:
            self.serial_conn.close()

    def _receive_data(self):
        """シリアルデータ受信（別スレッド）"""
        while self.running:
            try:
                if self.serial_conn and self.serial_conn.in_waiting > 0:
                    line = self.serial_conn.readline().decode("utf-8").strip()
                    if "," in line:
                        timestamp_str, force_str = line.split(",", 1)
                        timestamp = float(timestamp_str) / 1000.0  # ms -> s
                        force = float(force_str)
                        self.data_received.emit(timestamp, force)

            except Exception as e:
                print(f"データ受信エラー: {e}")

            time.sleep(0.001)  # 1ms待機

    def _dummy_data(self):
        """ダミーデータ生成（テスト用）"""
        import math

        start_time = time.time()
        counter = 0

        while self.running:
            current_time = time.time() - start_time

            # 山形の波形を生成（5秒周期で山が現れる）
            if counter % 500 == 0:  # 5秒に1回山を生成
                mountain_phase = 0

            if counter % 500 < 100:  # 1秒間山を描画
                force = 20 + 30 * math.sin(math.pi * (counter % 100) / 100)
            else:
                force = 0

            self.data_received.emit(current_time, max(0, force))
            counter += 1
            time.sleep(0.01)  # 10ms間隔


class AdminModeWidget(QWidget):
    """管理者モード：リアルタイムモニタリング画面"""

    def __init__(self):
        super().__init__()
        self.init_ui()
        self.init_data()

    def init_ui(self):
        """UI初期化"""
        layout = QVBoxLayout()

        # タイトル
        title = QLabel("管理者モード - リアルタイムモニタリング")
        title.setFont(QFont("Arial", 16, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # グラフ設定
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setLabel("left", "力 [N]")
        self.plot_widget.setLabel("bottom", "時間 [s]")
        self.plot_widget.setYRange(0, 200, padding=0)  # Y軸固定スケール
        self.plot_widget.showGrid(x=True, y=True)

        # プロット線
        self.plot_line = self.plot_widget.plot([], [], pen="b", width=2)

        layout.addWidget(self.plot_widget)
        self.setLayout(layout)

    def init_data(self):
        """データ管理初期化"""
        self.data_buffer = deque(maxlen=500)  # 5秒分（10ms間隔想定）

    def update_data(self, timestamp, force):
        """データ更新"""
        self.data_buffer.append((timestamp, force))

        # 直近5秒分のデータのみ表示
        if len(self.data_buffer) >= 2:
            latest_time = self.data_buffer[-1][0]
            # 5秒より古いデータを除去
            while self.data_buffer and latest_time - self.data_buffer[0][0] > 5.0:
                self.data_buffer.popleft()

        # グラフ更新
        self.update_plot()

    def update_plot(self):
        """グラフ描画更新"""
        if len(self.data_buffer) < 2:
            return

        times = [data[0] for data in self.data_buffer]
        forces = [data[1] for data in self.data_buffer]

        self.plot_line.setData(times, forces)

        # X軸範囲を最新5秒に設定
        latest_time = times[-1]
        self.plot_widget.setXRange(latest_time - 5.0, latest_time, padding=0)


class UserModeWidget(QWidget):
    """ユーザーモード：山の確認用画面"""

    def __init__(self):
        super().__init__()
        self.init_ui()
        self.init_data()

    def init_ui(self):
        """UI初期化"""
        layout = QVBoxLayout()

        # タイトル
        title = QLabel("ユーザーモード - 山の確認")
        title.setFont(QFont("Arial", 16, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # カウントダウン表示用ラベル
        self.countdown_label = QLabel("")
        self.countdown_label.setFont(QFont("Arial", 48, QFont.Bold))
        self.countdown_label.setAlignment(Qt.AlignCenter)
        self.countdown_label.setStyleSheet("color: red;")
        layout.addWidget(self.countdown_label)

        # ステータス表示
        self.status_label = QLabel("準備中...")
        self.status_label.setFont(QFont("Arial", 12))
        self.status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_label)

        # グラフ設定
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setLabel("left", "力 [N]")
        self.plot_widget.setLabel("bottom", "時間 [s]")
        self.plot_widget.showGrid(x=True, y=True)

        # プロット線
        self.plot_line = self.plot_widget.plot([], [], pen="r", width=3)

        layout.addWidget(self.plot_widget)
        self.setLayout(layout)

        # カウントダウンタイマー
        self.countdown_timer = QTimer()
        self.countdown_timer.timeout.connect(self.update_countdown)

        # 静止表示タイマー
        self.freeze_timer = QTimer()
        self.freeze_timer.timeout.connect(self.end_freeze_display)

    def init_data(self):
        """データ管理初期化"""
        self.reset_state()

    def reset_state(self):
        """状態リセット"""
        self.state = "countdown"  # countdown, detecting, frozen, realtime
        self.countdown_value = 3
        self.mountain_data = []
        self.current_mountain = []
        self.in_mountain = False
        self.mountain_found = False
        self.data_buffer = deque(maxlen=1000)

    def start_user_mode(self):
        """ユーザーモード開始"""
        self.reset_state()
        self.plot_widget.hide()  # グラフを非表示
        self.start_countdown()

    def start_countdown(self):
        """カウントダウン開始"""
        self.state = "countdown"
        self.countdown_value = 3
        self.countdown_label.show()
        self.status_label.setText("まもなく開始...")
        self.update_countdown()
        self.countdown_timer.start(1000)  # 1秒間隔

    def update_countdown(self):
        """カウントダウン更新"""
        if self.countdown_value > 0:
            self.countdown_label.setText(str(self.countdown_value))
            self.countdown_value -= 1
        else:
            self.countdown_label.setText("Start!")
            self.countdown_timer.stop()
            # 1秒後にカウントダウンを隠してグラフ表示開始
            QTimer.singleShot(1000, self.start_detection)

    def start_detection(self):
        """山の検出開始"""
        self.countdown_label.hide()
        self.plot_widget.show()
        self.state = "detecting"
        self.status_label.setText("最初の山を検出中...")

    def update_data(self, timestamp, force):
        """データ更新"""
        if self.state == "countdown":
            return

        self.data_buffer.append((timestamp, force))

        if self.state == "detecting":
            self.detect_mountain(timestamp, force)
        elif self.state == "frozen":
            # 静止表示中は更新しない
            pass
        elif self.state == "realtime":
            self.update_realtime_plot()

    def detect_mountain(self, timestamp, force):
        """山の検出処理"""
        if self.mountain_found:
            return

        # 前回の値を取得
        prev_force = 0
        if len(self.data_buffer) >= 2:
            prev_force = self.data_buffer[-2][1]

        # 山の開始検出: 0 → 正の値
        if not self.in_mountain and prev_force <= 0 and force > 0:
            self.in_mountain = True
            self.current_mountain = [(timestamp, force)]
            self.status_label.setText("山を検出中...")

        # 山の継続
        elif self.in_mountain and force > 0:
            self.current_mountain.append((timestamp, force))

        # 山の終了検出: 正の値 → 0
        elif self.in_mountain and force <= 0:
            self.current_mountain.append((timestamp, force))
            self.mountain_found = True
            self.mountain_data = self.current_mountain.copy()
            self.display_mountain()

    def display_mountain(self):
        """山の波形を15秒間静止表示"""
        self.state = "frozen"
        self.status_label.setText("山を検出しました！15秒間表示中...")

        # 山のデータをプロット
        if self.mountain_data:
            times = [data[0] for data in self.mountain_data]
            forces = [data[1] for data in self.mountain_data]
            self.plot_line.setData(times, forces)

            # X軸とY軸の範囲を山のデータに合わせて設定
            if len(times) >= 2:
                time_range = max(times) - min(times)
                margin = time_range * 0.1  # 10%のマージン
                self.plot_widget.setXRange(
                    min(times) - margin, max(times) + margin, padding=0
                )

                max_force = max(forces) if forces else 100
                self.plot_widget.setYRange(0, max_force * 1.2, padding=0)

        # 15秒後に通常モードに戻る
        self.freeze_timer.start(15000)  # 15秒

    def end_freeze_display(self):
        """静止表示終了、リアルタイム表示開始"""
        self.freeze_timer.stop()
        self.state = "realtime"
        self.status_label.setText("リアルタイム表示中（以降の山は無視）")

    def update_realtime_plot(self):
        """リアルタイムプロット更新"""
        if len(self.data_buffer) < 2:
            return

        # 直近5秒分のデータを表示
        latest_time = self.data_buffer[-1][0]
        filtered_data = [(t, f) for t, f in self.data_buffer if latest_time - t <= 5.0]

        if len(filtered_data) >= 2:
            times = [data[0] for data in filtered_data]
            forces = [data[1] for data in filtered_data]

            self.plot_line.setData(times, forces)
            self.plot_widget.setXRange(latest_time - 5.0, latest_time, padding=0)

            max_force = max(forces) if forces else 100
            self.plot_widget.setYRange(0, max(max_force * 1.2, 200), padding=0)


class MainWindow(QMainWindow):
    """メインウィンドウ"""

    def __init__(self):
        super().__init__()
        self.init_ui()
        self.init_data_receiver()

    def init_ui(self):
        """UI初期化"""
        self.setWindowTitle("Arduino床反力データ可視化システム")
        self.setGeometry(100, 100, 1200, 800)

        # 中央ウィジェット
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # レイアウト
        main_layout = QVBoxLayout()

        # モード切替ボタン
        button_layout = QHBoxLayout()

        self.admin_button = QPushButton("管理者モード")
        self.admin_button.clicked.connect(self.switch_to_admin)
        self.admin_button.setMinimumHeight(40)

        self.user_button = QPushButton("ユーザーモード")
        self.user_button.clicked.connect(self.switch_to_user)
        self.user_button.setMinimumHeight(40)

        button_layout.addWidget(self.admin_button)
        button_layout.addWidget(self.user_button)

        main_layout.addLayout(button_layout)

        # モード表示エリア
        self.admin_widget = AdminModeWidget()
        self.user_widget = UserModeWidget()

        main_layout.addWidget(self.admin_widget)
        main_layout.addWidget(self.user_widget)

        central_widget.setLayout(main_layout)

        # 初期状態：管理者モード
        self.switch_to_admin()

    def init_data_receiver(self):
        """データ受信機初期化"""
        self.data_receiver = DataReceiver()
        self.data_receiver.data_received.connect(self.on_data_received)

        # リアルタイム更新タイマー
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_display)
        self.update_timer.start(50)  # 20Hz更新（50ms間隔）

        # データ受信開始
        self.data_receiver.start_receiving()

    def switch_to_admin(self):
        """管理者モードに切替"""
        self.admin_widget.show()
        self.user_widget.hide()
        self.admin_button.setStyleSheet("background-color: lightblue;")
        self.user_button.setStyleSheet("")
        self.current_mode = "admin"

    def switch_to_user(self):
        """ユーザーモードに切替"""
        self.admin_widget.hide()
        self.user_widget.show()
        self.user_button.setStyleSheet("background-color: lightgreen;")
        self.admin_button.setStyleSheet("")
        self.current_mode = "user"

        # ユーザーモード開始
        self.user_widget.start_user_mode()

    def on_data_received(self, timestamp, force):
        """データ受信イベント"""
        # 現在のモードに応じてデータを送信
        if self.current_mode == "admin":
            self.admin_widget.update_data(timestamp, force)
        elif self.current_mode == "user":
            self.user_widget.update_data(timestamp, force)

    def update_display(self):
        """表示更新（定期実行）"""
        # プロットウィジェットの更新を促進
        if self.current_mode == "admin":
            self.admin_widget.plot_widget.repaint()
        elif self.current_mode == "user":
            self.user_widget.plot_widget.repaint()

    def closeEvent(self, event):
        """アプリケーション終了時"""
        self.data_receiver.stop_receiving()
        event.accept()


def main():
    """メイン関数"""
    app = QApplication(sys.argv)

    # アプリケーションスタイル設定
    app.setStyle("Fusion")

    # メインウィンドウ作成・表示
    main_window = MainWindow()
    main_window.show()

    # イベントループ開始
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
