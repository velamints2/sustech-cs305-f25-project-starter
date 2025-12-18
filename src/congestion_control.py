import time
import math
import matplotlib.pyplot as plt


class CongestionController:
    """
    拥塞控制器：负责维护 cwnd 和 ssthresh，以及实现慢启动、
    拥塞避免和丢包后的窗口重置逻辑。
    """

    def __init__(self):
        # 初始状态
        self.cwnd: float = 1.0  # 拥塞窗口 (单位: packets)
        self.ssthresh: int = 64  # 慢启动阈值
        self.dup_ack_count: int = 0  # 重复 ACK 计数器

        # 绘图数据记录
        self.cwnd_history: list[tuple[float, float]] = []
        self.start_time = time.time()
        self.record_cwnd()

    def record_cwnd(self):
        """记录当前时间和窗口大小，用于最后生成图表"""
        self.cwnd_history.append((time.time() - self.start_time, self.cwnd))

    def get_cwnd(self) -> int:
        """返回当前的拥塞窗口大小 (向下取整，供 RDT 模块判断是否可发送)"""
        return int(self.cwnd)

    def on_new_ack(self):
        """
        供 RDT 调用：当收到新的（非重复）ACK 时调用。
        严格实现 4.4.1 (慢启动) 和 4.4.2 (拥塞避免) 逻辑。
        """
        # 重置重复 ACK 计数
        self.dup_ack_count = 0

        # 判断状态
        if self.cwnd < self.ssthresh:
            # --- 慢启动 ---
            # "With each ACK received, cwnd increases by 1."
            self.cwnd += 1.0
        else:
            # --- 拥塞避免 ---
            # "cwnd increases by 1/cwnd packet upon receiving ACK."
            self.cwnd += 1.0 / self.cwnd

        self.record_cwnd()

    def on_duplicate_ack(self) -> bool:
        """
        供 RDT 调用：当收到重复 ACK 时调用。
        返回: True 表示触发了快速重传 (Fast Retransmit)。
        """
        self.dup_ack_count += 1

        # 快速重传触发条件: 3个重复ACK
        if self.dup_ack_count == 3:
            # 触发 Fast Retransmit 机制，处理方式与 Timeout 相同 (TCP Tahoe)
            self._handle_loss_event()
            return True

        return False

    def on_timeout(self):
        """
        供 RDT 调用：当 RDT 模块检测到超时事件时调用。
        """
        self._handle_loss_event()

    def _handle_loss_event(self):
        """
        私有方法：处理丢包事件 (超时或 3 个重复 ACK)。
        严格遵循文档 4.4 描述 (TCP Tahoe 风格的重置)。
        """
        # 1. 更新 ssthresh: ssthresh = max(floor(cwnd/2), 2)
        self.ssthresh = max(math.floor(self.cwnd / 2), 2)

        # 2. 重置 cwnd: cwnd is then set to 1
        self.cwnd = 1.0

        self.record_cwnd()

    def plot_analysis(self, filename="concurrency_analysis.png"):
        """
        任务结束时调用：生成拥塞窗口变化图。
        文档要求: "A plot demonstrating window size changes... is required"
        """
        try:
            times = [x[0] for x in self.cwnd_history]
            cwnds = [x[1] for x in self.cwnd_history]

            plt.figure(figsize=(10, 6))
            plt.plot(times, cwnds, label='cwnd')
            plt.title("Congestion Window Analysis")
            plt.xlabel("Time (s)")
            plt.ylabel("Window Size (packets)")
            plt.legend()
            plt.grid(True)
            plt.savefig(filename)
            plt.close()
            print(f"Congestion control analysis saved to {filename}")
        except Exception as e:
            print(f"Failed to plot analysis: {e}")