#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Arduino床反力データ リアルタイム可視化アプリ
メイン画面：リアルタイムデータ表示
別ウィンドウ：山検出時に過去3名分+ボルトデータと共に表示
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

            if counter % 500 < 15:  # 5秒周期で最初の0.3秒間だけ山を描画
                # 山の中での位置を計算（0から29まで）
                mountain_position = counter % 500  # 500周期の中での位置
                force = 2500 * math.sin(math.pi * mountain_position / 15)
            else:
                force = 0

            self.data_received.emit(current_time, max(0, force))
            counter += 1
            time.sleep(0.01)  # 10ms間隔


class MountainDisplayWindow(QMainWindow):
    """山検出時に表示される別ウィンドウ"""

    def __init__(self):
        super().__init__()
        self.init_ui()
        self.load_bolt_data()
        self.past_mountains = []  # 過去3名分の山データ

    def init_ui(self):
        """UI初期化"""
        self.setWindowTitle("山の波形表示")
        self.setGeometry(150, 150, 1000, 600)

        # 中央ウィジェット
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout()

        # タイトル
        title = QLabel("検出された山の波形")
        title.setFont(QFont("Arial", 16, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # ステータス表示
        self.status_label = QLabel("")
        self.status_label.setFont(QFont("Arial", 12))
        self.status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_label)

        # 閉じるボタン
        self.close_button = QPushButton("閉じる")
        self.close_button.setMinimumHeight(40)
        self.close_button.clicked.connect(self.close)
        layout.addWidget(self.close_button)

        # グラフ設定
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setLabel("left", "力 [N]")
        self.plot_widget.setLabel("bottom", "時間 [s]")
        self.plot_widget.showGrid(x=True, y=True)

        # プロット線（現在 + 過去3名分 + ボルト）
        self.current_line = self.plot_widget.plot(
            [], [], pen="r", width=3
        )  # 現在の測定
        self.past_lines = [
            self.plot_widget.plot([], [], pen="orange", width=2),  # 過去1
            self.plot_widget.plot([], [], pen="yellow", width=2),  # 過去2
            self.plot_widget.plot([], [], pen="pink", width=2),  # 過去3
        ]
        self.bolt_line = self.plot_widget.plot([], [], pen="g", width=3)  # ボルト

        layout.addWidget(self.plot_widget)
        central_widget.setLayout(layout)

        # 自動閉じタイマー
        self.auto_close_timer = QTimer()
        self.auto_close_timer.timeout.connect(self.close)

    def load_bolt_data(self):
        """ボルトのCSVデータを読み込み"""
        # ボルトのデータ（CSVから）
        bolt_data = [
            (0, 0),
            (0.004563256, 0.167771967),
            (0.009126359, 0.25165795),
            (0.013689615, 0.419429917),
            (0.018425183, 0.297413941),
            (0.02281753, 1.526724896),
            (0.022824592, 5.410645923),
            (0.023228403, 18.37103034),
            (0.024737719, 11.95375262),
            (0.027465331, 48.19249741),
            (0.027109108, 61.40453978),
            (0.027893851, 74.74241112),
            (0.038256399, 336.6176738),
            (0.037424403, 297.2919248),
            (0.037906993, 353.5794196),
            (0.037840874, 317.2148459),
            (0.040253902, 389.5665065),
            (0.041829909, 419.8283749),
            (0.043374267, 432.6839019),
            (0.043017815, 445.7701153),
            (0.044557499, 456.0545368),
            (0.044955613, 465.8817798),
            (0.04726664, 482.134689),
            (0.046874482, 475.5831937),
            (0.048199852, 493.476074),
            (0.04832469, 488.9399394),
            (0.049413991, 497.9951317),
            (0.052804019, 495.2313882),
            (0.052227118, 491.6389709),
            (0.052220552, 488.0276794),
            (0.052239198, 498.2827408),
            (0.053737394, 485.7501749),
            (0.053726596, 479.8110473),
            (0.05673095, 459.1247638),
            (0.057094083, 449.7127565),
            (0.058221734, 442.5153391),
            (0.05820462, 433.1033318),
            (0.058946962, 423.1208998),
            (0.059676369, 406.0249364),
            (0.061560599, 396.6758435),
            (0.062670107, 379.5001885),
            (0.062654092, 370.6921602),
            (0.063781217, 363.2053362),
            (0.063769206, 356.599315),
            (0.065658996, 350.3078663),
            (0.066621606, 341.9672028),
            (0.067156329, 337.3007454),
            (0.067160761, 339.7382324),
            (0.068517621, 333.1246615),
            (0.068283425, 329.7977434),
            (0.068404149, 326.484247),
            (0.068778065, 323.0029787),
            (0.069405631, 319.6055964),
            (0.071671739, 311.1540836),
            (0.072802067, 305.4288652),
            (0.073064411, 300.3357876),
            (0.074301239, 293.4331696),
            (0.073534113, 289.7841293),
            (0.076184715, 283.6688411),
            (0.076172635, 277.0250713),
            (0.077301948, 270.7420111),
            (0.077669642, 263.8381947),
            (0.07803735, 256.9427669),
            (0.078405516, 250.298997),
            (0.07763331, 243.8565535),
            (0.08026567, 227.7085017),
            (0.081774299, 220.913737),
            (0.082141504, 213.7414855),
            (0.082886286, 205.1012292),
            (0.083252461, 197.3627472),
            (0.084363342, 180.942066),
            (0.086632463, 174.1473013),
            (0.086615533, 164.8359572),
            (0.087743229, 157.6637056),
            (0.088474322, 141.4946823),
            (0.088842374, 134.787998),
            (0.087688549, 127.5905806),
            (0.091081843, 111.6857982),
            (0.090714044, 118.5308944),
            (0.092209632, 104.5638782),
            (0.092197506, 97.89494251),
            (0.092945414, 90.97434889),
            (0.096308188, 58.2839812),
            (0.097817916, 52.09319563),
            (0.097805836, 45.44942575),
            (0.097798697, 41.52356173),
            (0.098928682, 35.60959991),
            (0.099192148, 31.13368352),
            (0.100814975, 27.3947654),
            (0.10099584, 22.30318581),
            (0.102321199, 19.27699896),
            (0.102205157, 15.2073304),
            (0.103445921, 10.46897072),
            (0.105110218, 5.637138078),
            (0.107043626, 2.422207768),
            (0.108261376, 0),
            (0.112281249, 0.035951136),
            (0.117115738, 0),
        ]

        # N(kg*9.8)に変換してボルトデータとして保存
        self.bolt_mountain = [(t, f * 9.8) for t, f in bolt_data]

    def show_mountain(self, mountain_data, mountain_count):
        """山の波形を表示"""
        # 過去データに保存
        self.past_mountains.append(mountain_data.copy())
        if len(self.past_mountains) > 3:
            self.past_mountains.pop(0)

        # ステータス更新
        self.status_label.setText(
            f"山#{mountain_count}を検出しました（15秒後に自動で閉じます）"
        )

        # 全ての波形を表示
        self.update_all_plots(mountain_data)

        # ウィンドウを表示
        self.show()
        self.raise_()
        self.activateWindow()

        # 15秒後に自動で閉じる
        self.auto_close_timer.start(15000)

    def update_all_plots(self, current_mountain_data):
        """すべての波形を更新"""
        # 現在の山データ
        if current_mountain_data:
            times = [data[0] for data in current_mountain_data]
            forces = [data[1] for data in current_mountain_data]
            # 時間を0からの相対時間に正規化
            base_time = times[0] if times else 0
            normalized_times = [t - base_time for t in times]
            self.current_line.setData(normalized_times, forces)

        # 過去3名分のデータ
        for i, past_data in enumerate(self.past_mountains[:-1]):  # 最新を除く
            if i < len(self.past_lines) and past_data:
                times = [data[0] for data in past_data]
                forces = [data[1] for data in past_data]
                # 時間を正規化
                base_time = times[0] if times else 0
                normalized_times = [t - base_time for t in times]
                self.past_lines[i].setData(normalized_times, forces)

        # 残りの過去データ線をクリア
        for i in range(len(self.past_mountains) - 1, len(self.past_lines)):
            self.past_lines[i].setData([], [])

        # ボルトのデータ
        if self.bolt_mountain:
            times = [data[0] for data in self.bolt_mountain]
            forces = [data[1] for data in self.bolt_mountain]
            self.bolt_line.setData(times, forces)

        # グラフの範囲調整
        self.adjust_plot_range()

    def adjust_plot_range(self):
        """グラフの表示範囲を調整"""
        all_times = []
        all_forces = []

        # 全データから時間と力の範囲を取得
        for past_data in self.past_mountains:
            if past_data:
                times = [data[0] for data in past_data]
                forces = [data[1] for data in past_data]
                base_time = times[0] if times else 0
                normalized_times = [t - base_time for t in times]
                all_times.extend(normalized_times)
                all_forces.extend(forces)

        if self.bolt_mountain:
            all_times.extend([data[0] for data in self.bolt_mountain])
            all_forces.extend([data[1] for data in self.bolt_mountain])

        if all_times and all_forces:
            time_margin = (max(all_times) - min(all_times)) * 0.1
            force_margin = max(all_forces) * 0.1

            self.plot_widget.setXRange(
                min(all_times) - time_margin, max(all_times) + time_margin, padding=0
            )
            self.plot_widget.setYRange(0, max(all_forces) + force_margin, padding=0)

    def closeEvent(self, event):
        """ウィンドウが閉じられる時"""
        self.auto_close_timer.stop()
        event.accept()


class RealtimeDisplayWidget(QWidget):
    """リアルタイムデータ表示ウィジェット"""

    mountain_detected = pyqtSignal(list)  # 山検出シグナル

    def __init__(self):
        super().__init__()
        self.init_ui()
        self.init_data()

    def init_ui(self):
        """UI初期化"""
        layout = QVBoxLayout()

        # タイトル
        title = QLabel("リアルタイム床反力データ")
        title.setFont(QFont("Arial", 16, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # ステータス表示
        self.status_label = QLabel("データ受信中...")
        self.status_label.setFont(QFont("Arial", 12))
        self.status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_label)

        # グラフ設定
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setLabel("left", "力 [N]")
        self.plot_widget.setLabel("bottom", "時間 [s]")
        self.plot_widget.setYRange(0, 5500, padding=0)  # Y軸固定スケール
        self.plot_widget.showGrid(x=True, y=True)

        # プロット線
        self.plot_line = self.plot_widget.plot([], [], pen="b", width=2)

        layout.addWidget(self.plot_widget)
        self.setLayout(layout)

    def init_data(self):
        """データ管理初期化"""
        self.data_buffer = deque(maxlen=500)  # 5秒分（10ms間隔想定）
        self.mountain_count = 0

        # 山検出用
        self.current_mountain = []
        self.in_mountain = False
        self.last_mountain_time = 0  # 最後に山を表示した時間

    def update_data(self, timestamp, force):
        """データ更新"""
        self.data_buffer.append((timestamp, force))

        # 山の検出処理
        self.detect_mountain(timestamp, force)

        # リアルタイムプロット更新
        self.update_plot()

    def detect_mountain(self, timestamp, force):
        """山の検出処理"""
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
            self.in_mountain = False

            # 15秒バッファーチェック
            current_time = time.time()
            if current_time - self.last_mountain_time >= 15.0:
                # 山を検出した（15秒経過している場合のみ）
                self.mountain_count += 1
                self.status_label.setText(
                    f"山#{self.mountain_count}を検出！別ウィンドウで表示中..."
                )

                # 山検出シグナル発火
                self.mountain_detected.emit(self.current_mountain.copy())

                # 最後の山表示時間を更新
                self.last_mountain_time = current_time

                # 3秒後にステータスを戻す
                QTimer.singleShot(
                    3000, lambda: self.status_label.setText("データ受信中...")
                )
            else:
                # 15秒以内の場合は無視
                remaining_time = 15.0 - (current_time - self.last_mountain_time)
                self.status_label.setText(
                    f"山を検出したが無視中（残り{remaining_time:.1f}秒）..."
                )

                # 3秒後にステータスを戻す
                QTimer.singleShot(
                    3000, lambda: self.status_label.setText("データ受信中...")
                )

    def update_plot(self):
        """グラフ描画更新"""
        if len(self.data_buffer) < 2:
            return

        # 直近5秒分のデータのみ表示
        latest_time = self.data_buffer[-1][0]
        # 5秒より古いデータを除去
        while self.data_buffer and latest_time - self.data_buffer[0][0] > 5.0:
            self.data_buffer.popleft()

        times = [data[0] for data in self.data_buffer]
        forces = [data[1] for data in self.data_buffer]

        self.plot_line.setData(times, forces)

        # X軸範囲を最新5秒に設定
        self.plot_widget.setXRange(latest_time - 5.0, latest_time, padding=0)


class MainWindow(QMainWindow):
    """メインウィンドウ"""

    def __init__(self):
        super().__init__()
        self.init_ui()
        self.init_data_receiver()

    def init_ui(self):
        """UI初期化"""
        self.setWindowTitle("Arduino床反力データ可視化システム（リアルタイム）")
        self.setGeometry(100, 100, 1200, 800)

        # リアルタイム表示ウィジェット
        self.realtime_widget = RealtimeDisplayWidget()
        self.setCentralWidget(self.realtime_widget)

        # 山表示ウィンドウ
        self.mountain_window = MountainDisplayWindow()

        # シグナル接続
        self.realtime_widget.mountain_detected.connect(self.on_mountain_detected)

    def init_data_receiver(self):
        """データ受信機初期化"""
        self.data_receiver = DataReceiver()
        self.data_receiver.data_received.connect(self.realtime_widget.update_data)

        # リアルタイム更新タイマー
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_display)
        self.update_timer.start(50)  # 20Hz更新（50ms間隔）

        # データ受信開始
        self.data_receiver.start_receiving()

    def on_mountain_detected(self, mountain_data):
        """山が検出された時の処理"""
        self.mountain_window.show_mountain(
            mountain_data, self.realtime_widget.mountain_count
        )

    def update_display(self):
        """表示更新（定期実行）"""
        self.realtime_widget.plot_widget.repaint()

    def closeEvent(self, event):
        """アプリケーション終了時"""
        self.data_receiver.stop_receiving()
        self.mountain_window.close()
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
