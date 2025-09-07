#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Arduino床反力データ フル画面リアルタイム可視化アプリ
フル画面3分割レイアウト：
- 上左: 最高値表示（10秒有効）
- 上右: 最高値の波形表示
- 下: リアルタイムデータ表示
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
    QFrame,
)
from PyQt5.QtCore import QTimer, pyqtSignal, QObject, Qt
from PyQt5.QtGui import QFont, QPalette
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
                        force = force * 9.8  # kgからNへ
                        self.data_received.emit(timestamp, force)

            except Exception as e:
                print(f"データ受信エラー: {e}")

            time.sleep(0.001)  # 1ms待機

    def _dummy_data(self):
        """ダミーデータ生成（テスト用）"""
        import math

        start_time = time.time()
        counter = 0

        # 山のパターン（小中大中小）
        mountain_patterns = [1000, 2000, 3000, 2000, 1000]  # 各山の最大値
        pattern_index = 0

        while self.running:
            current_time = time.time() - start_time

            # 3秒周期で山が現れる（300カウント = 3秒）
            cycle_position = counter % 300  # 3秒周期

            if cycle_position == 0:  # 新しい山の開始
                pattern_index = (pattern_index + 1) % len(mountain_patterns)

            if cycle_position < 20:  # 3秒周期で最初の0.2秒間だけ山を描画
                # 現在の山の高さを取得
                current_max = mountain_patterns[pattern_index]
                # 山の形を計算
                force = current_max * math.sin(math.pi * cycle_position / 20)
            else:
                force = 0

            self.data_received.emit(current_time, max(0, force))
            counter += 1
            time.sleep(0.01)  # 10ms間隔


class MaxValueWidget(QFrame):
    """最高値表示ウィジェット"""

    def __init__(self):
        super().__init__()
        self.init_ui()
        self.init_data()

    def init_ui(self):
        """UI初期化"""
        # 青色の枠線設定
        self.setStyleSheet(
            "QFrame { border: 4px solid #2E86AB; background-color: black; }"
        )

        layout = QVBoxLayout()

        # タイトル
        title = QLabel("最高値 / Max Value")
        title.setFont(QFont("Arial", 24, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("color: #2E86AB; border: none;")
        layout.addWidget(title)

        # 最高値表示
        self.max_value_label = QLabel("0 N")
        self.max_value_label.setFont(QFont("Arial", 48, QFont.Bold))
        self.max_value_label.setAlignment(Qt.AlignCenter)
        self.max_value_label.setStyleSheet(
            "color: #d32f2f; border: none; margin: 20px;"
        )
        layout.addWidget(self.max_value_label)

        # 有効時間表示
        self.timer_label = QLabel("10.0秒")
        self.timer_label.setFont(QFont("Arial", 14))
        self.timer_label.setAlignment(Qt.AlignCenter)
        self.timer_label.setStyleSheet("color: #666; border: none;")
        layout.addWidget(self.timer_label)

        self.setLayout(layout)

    def init_data(self):
        """データ初期化"""
        self.max_force = 0
        self.max_timestamp = 0
        self.max_mountain_data = []

    def update_max_value(self, timestamp, force, mountain_data=None):
        """最高値を更新"""
        # 10秒経過チェック
        if timestamp - self.max_timestamp > 10.0:
            # 10秒経過したら最高値をリセット
            self.max_force = 0
            self.max_mountain_data = []

        # 新しい最高値チェック
        if force > self.max_force:
            self.max_force = force
            self.max_timestamp = timestamp
            if mountain_data:
                self.max_mountain_data = mountain_data.copy()

        # 表示更新
        self.max_value_label.setText(f"{self.max_force:.0f} N")

        # 残り時間計算
        remaining_time = max(0, 10.0 - (timestamp - self.max_timestamp))
        self.timer_label.setText(f"{remaining_time:.1f}秒/sec")

        return self.max_mountain_data


class PastWaveformsWidget(QFrame):
    """過去3回分の波形表示ウィジェット"""

    def __init__(self):
        super().__init__()
        self.init_ui()
        self.load_bolt_data()
        self.past_mountains = []  # 過去3回分の山データ

    def init_ui(self):
        """UI初期化"""
        # 青色の枠線設定（暗い背景に対応）
        self.setStyleSheet(
            "QFrame { border: 4px solid #2E86AB; background-color: black; }"
        )

        layout = QVBoxLayout()

        # タイトル
        title = QLabel("波形 / Waveforms")
        title.setFont(QFont("Arial", 24, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("color: #2E86AB; border: none; margin: 10px;")
        layout.addWidget(title)

        # グラフ設定
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setLabel(
            "left", "力 [N]", **{"font-size": "14pt", "color": "white"}
        )
        self.plot_widget.setLabel(
            "bottom", "時間 [s]", **{"font-size": "14pt", "color": "white"}
        )
        self.plot_widget.showGrid(x=True, y=True)
        self.plot_widget.setStyleSheet("border: none; background-color: #1a1a1a;")
        self.plot_widget.setBackground("black")

        # 凡例追加
        self.plot_widget.addLegend(labelTextSize="12pt")

        # プロット線（ボルトを最初に追加して後ろに配置）
        self.bolt_line = self.plot_widget.plot(
            [],
            [],
            pen=pg.mkPen("g", width=4),
            name="ウサイン・ボルト / Usain Bolt",
        )

        # 過去3回分の線（新しい順：赤→橙→黄）
        self.past_lines = [
            self.plot_widget.plot(
                [], [], pen=pg.mkPen("r", width=8), name="最新 / Latest"
            ),
            self.plot_widget.plot(
                [], [], pen=pg.mkPen("orange", width=4), name="1つ前 / Previous"
            ),
            self.plot_widget.plot(
                [], [], pen=pg.mkPen("yellow", width=4), name="2つ前 / 2nd Previous"
            ),
        ]

        layout.addWidget(self.plot_widget)
        self.setLayout(layout)

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

        # ボルトデータを表示
        if self.bolt_mountain:
            times = [data[0] for data in self.bolt_mountain]
            forces = [data[1] for data in self.bolt_mountain]
            self.bolt_line.setData(times, forces)

    def add_new_waveform(self, mountain_data):
        """新しい波形を追加"""
        if mountain_data:
            # 新しい山データを先頭に追加
            self.past_mountains.insert(0, mountain_data.copy())

            # 確実に3つまでに制限
            self.past_mountains = self.past_mountains[:3]

            # 全ての波形を更新
            self.update_all_waveforms()

    def update_all_waveforms(self):
        """全ての波形を更新"""
        # 過去の山データを表示
        for i, past_data in enumerate(self.past_mountains):
            if i < len(self.past_lines) and past_data:
                times = [data[0] for data in past_data]
                forces = [data[1] for data in past_data]

                # 時間を0からの相対時間に正規化
                base_time = times[0] if times else 0
                normalized_times = [t - base_time for t in times]

                self.past_lines[i].setData(normalized_times, forces)
            elif i < len(self.past_lines):
                # データがない場合は空にする
                self.past_lines[i].setData([], [])

        # 使用されていない線をクリア
        for i in range(len(self.past_mountains), len(self.past_lines)):
            self.past_lines[i].setData([], [])

        # グラフの範囲調整
        self.adjust_plot_range()

    def adjust_plot_range(self):
        """グラフの表示範囲を調整"""
        all_times = []
        all_forces = []

        # 過去の山データから時間と力を収集（最新の3つのみ）
        for i, past_data in enumerate(self.past_mountains[:3]):  # 最新3つのみ
            if past_data:
                times = [data[0] for data in past_data]
                forces = [data[1] for data in past_data]

                # 正規化された時間（0ベース）を追加
                if times:
                    base_time = times[0]
                    normalized_times = [t - base_time for t in times]
                    all_times.extend(normalized_times)
                    all_forces.extend(forces)

        # ボルトデータも範囲に含める
        if self.bolt_mountain:
            all_times.extend([data[0] for data in self.bolt_mountain])
            all_forces.extend([data[1] for data in self.bolt_mountain])

        if all_times and all_forces:
            # より安定した範囲設定
            max_time = max(all_times)
            max_force = max(all_forces)

            # 固定の範囲を設定（データに依存しすぎないように）
            self.plot_widget.setXRange(0, max(0.12, max_time * 1.1), padding=0)
            self.plot_widget.setYRange(0, max(5000, max_force * 1.1), padding=0)
        else:
            # デフォルト範囲
            self.plot_widget.setXRange(0, 0.12, padding=0)
            self.plot_widget.setYRange(0, 5000, padding=0)


class RealtimeDisplayWidget(QFrame):
    """リアルタイムデータ表示ウィジェット"""

    mountain_detected = pyqtSignal(list)  # 山検出シグナル
    max_value_updated = pyqtSignal(float, float, list)  # 最高値更新シグナル

    def __init__(self):
        super().__init__()
        self.init_ui()
        self.init_data()

    def init_ui(self):
        """UI初期化"""
        # 青色の枠線設定
        self.setStyleSheet(
            "QFrame { border: 4px solid #2E86AB; background-color: black; }"
        )

        layout = QVBoxLayout()

        # タイトル
        title = QLabel("床反力データ / GRF Data")
        title.setFont(QFont("Arial", 24, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("color: #2E86AB; border: none; margin: 10px;")
        layout.addWidget(title)

        # ステータス表示
        self.status_label = QLabel("データ受信中...")
        self.status_label.setFont(QFont("Arial", 12))
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("color: #666; border: none;")
        layout.addWidget(self.status_label)

        # グラフ設定
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setLabel("left", "力 [N]", **{"font-size": "12pt"})
        self.plot_widget.setLabel("bottom", "時間 [s]", **{"font-size": "12pt"})
        self.plot_widget.setYRange(0, 5500, padding=0)  # Y軸固定スケール
        self.plot_widget.showGrid(x=True, y=True)
        self.plot_widget.setStyleSheet("border: none;")

        # プロット線
        self.plot_line = self.plot_widget.plot([], [], pen=pg.mkPen("b", width=5))

        layout.addWidget(self.plot_widget)
        self.setLayout(layout)

    def init_data(self):
        """データ管理初期化"""
        self.data_buffer = deque(maxlen=500)  # 5秒分（10ms間隔想定）

        # 山検出用
        self.current_mountain = []
        self.in_mountain = False
        self.last_mountain_timestamp = 0  # 最後に山を検出したタイムスタンプ

    def update_data(self, timestamp, force):
        """データ更新"""
        self.data_buffer.append((timestamp, force))

        # 山の検出処理
        self.detect_mountain(timestamp, force)

        # 最高値更新シグナル発火
        self.max_value_updated.emit(timestamp, force, [])

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
            self.status_label.setText("山を検出中... / Detecting...")

        # 山の継続
        elif self.in_mountain and force > 0:
            self.current_mountain.append((timestamp, force))

        # 山の終了検出: 正の値 → 0
        elif self.in_mountain and force <= 0:
            self.current_mountain.append((timestamp, force))
            self.in_mountain = False

            # 1秒バッファーチェック
            if timestamp - self.last_mountain_timestamp >= 1.0:
                # 山を検出した（1秒経過している場合のみ）
                self.status_label.setText(f"山を検出 / Detected")

                # 山検出シグナル発火
                self.mountain_detected.emit(self.current_mountain.copy())

                # 最高値更新（山の最大値を取得）
                max_force_in_mountain = max([data[1] for data in self.current_mountain])
                self.max_value_updated.emit(
                    timestamp, max_force_in_mountain, self.current_mountain.copy()
                )

                # 最後の山のタイムスタンプを更新
                self.last_mountain_timestamp = timestamp

                # 3秒後にステータスを戻す
                QTimer.singleShot(
                    3000,
                    lambda: self.status_label.setText(
                        "データ受信中... / Receiving Data..."
                    ),
                )
            else:
                # 1秒以内の場合は無視
                remaining_time = 1.0 - (timestamp - self.last_mountain_timestamp)
                self.status_label.setText(
                    f"山を検出したが無視中（残り{remaining_time:.1f}秒）..."
                )

                # 3秒後にステータスを戻す
                QTimer.singleShot(
                    3000,
                    lambda: self.status_label.setText(
                        "データ受信中... / Receiving Data..."
                    ),
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
        self.setWindowTitle("フル画面床反力データ可視化システム")

        # フル画面設定
        self.showFullScreen()

        # ESCキーで終了できるように
        self.setFocusPolicy(Qt.StrongFocus)

        # 中央ウィジェット
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # 背景色設定
        central_widget.setStyleSheet("background-color: black")

        # メインレイアウト（縦分割）
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        # 上部レイアウト（横分割：左1、右2の比率）
        upper_layout = QHBoxLayout()

        # 上左：最高値表示ウィジェット
        self.max_value_widget = MaxValueWidget()
        upper_layout.addWidget(self.max_value_widget, 1)  # 比率1

        # 上右：過去3回分波形表示ウィジェット
        self.past_waveforms_widget = PastWaveformsWidget()
        upper_layout.addWidget(self.past_waveforms_widget, 2)  # 比率2

        # 下部：リアルタイム表示ウィジェット
        self.realtime_widget = RealtimeDisplayWidget()

        # レイアウト配置（上:下 = 1:1の比率）
        main_layout.addLayout(upper_layout, 1)
        main_layout.addWidget(self.realtime_widget, 1)

        central_widget.setLayout(main_layout)

        # シグナル接続
        self.realtime_widget.mountain_detected.connect(self.on_mountain_detected)
        self.realtime_widget.max_value_updated.connect(self.on_max_value_updated)

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
        # 過去3回分波形ウィジェットに新しい波形を追加
        self.past_waveforms_widget.add_new_waveform(mountain_data)

    def on_max_value_updated(self, timestamp, force, mountain_data):
        """最高値が更新された時の処理"""
        # 最高値ウィジェットを更新
        self.max_value_widget.update_max_value(timestamp, force, mountain_data)

    def update_display(self):
        """表示更新（定期実行）"""
        # 必要に応じて追加の更新処理を行う
        pass

    def keyPressEvent(self, event):
        """キーイベント処理"""
        if event.key() == Qt.Key_Escape:
            self.close()
        super().keyPressEvent(event)

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
