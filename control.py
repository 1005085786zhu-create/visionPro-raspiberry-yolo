#!/usr/bin/env python3
"""
Yahboom DOFBOT 手势控制TCP服务器（地面夹取优化版 + 独立舵机控制 + WiFi适配）
✅ 手臂下弯可碰到地面
✅ 新增一键到夹取位置
✅ 保留所有原有功能
✅ 新增2-6号舵机独立前倾/后仰控制（适配Vision Pro）
✅ 修复端口占用报错
✅ 修复树莓派真实IP获取错误
✅ 【新增】滑动摇杆绝对角度控制（S2:90 格式）
✅ 【新增】WiFi更换后自动显示新IP + 多网卡IP检测
"""

import socket
import time
import netifaces  # 新增：需安装 pip install netifaces
from Arm_Lib import Arm_Device

# ====================== 核心修改1：调整安全角度范围 ======================
SAFE_LIMITS = {
    1: (0, 180),      # 底座
    2: (30, 165),     # 大臂（上限从150→165，允许向下弯更多）
    3: (20, 150),     # 小臂（下限从30→20，允许向下弯更多）
    4: (0, 180),      # 手腕
    5: (0, 270),      # 夹爪旋转
    6: (30, 150)      # 夹爪
}

# 标准垂直复位位置
RESET_POSITION = [90, 90, 90, 90, 90, 30]

# 地面夹取最佳位置
PICK_POSITION = [90, 160, 25, 90, 90, 30]

# ====================== 机械臂控制类（保留所有旧代码） ======================
class DofbotGestureController:
    def __init__(self):
        self.arm = Arm_Device()
        print("✅ Yahboom DOFBOT 机械臂初始化成功")
        
        self.current_angles = RESET_POSITION.copy()
        self.running = True
        
        print("🔄 正在强制复位到标准垂直位置...")
        self.force_reset()
        print("✅ 复位完成，所有关节已与地面垂直")
        
    def _clamp_angle(self, servo_id, angle):
        min_angle, max_angle = SAFE_LIMITS[servo_id]
        return max(min_angle, min(max_angle, int(angle)))
    
    def _write_servo_angle(self, servo_id, angle, duration=500):
        angle = self._clamp_angle(servo_id, angle)
        try:
            self.arm.Arm_serial_servo_write(servo_id, angle, duration)
            time.sleep(0.05)
            self.arm.Arm_serial_servo_write(servo_id, angle, duration)
            time.sleep(duration / 1000 + 0.2)
            self.current_angles[servo_id-1] = angle
            return True
        except Exception as e:
            print(f"❌ 舵机{servo_id}写入失败: {e}")
            return False

    # 原有独立舵机精细控制方法（保留）
    def adjust_single_servo(self, servo_id, step):
        new_angle = self.current_angles[servo_id - 1] + step
        if self._write_servo_angle(servo_id, new_angle, 300):
            return f"舵机{servo_id} → {new_angle}° ({step:+d}°)"
        return f"❌ 舵机{servo_id}调整失败"

    # 滑块专用 绝对角度控制（保留）
    def set_servo_absolute(self, servo_id, angle):
        angle = self._clamp_angle(servo_id, angle)
        if self._write_servo_angle(servo_id, angle, 300):
            return f"✅ 舵机{servo_id} 绝对角度 → {angle}°"
        return f"❌ 舵机{servo_id} 绝对角度设置失败"
    
    def force_reset(self):
        self.arm.Arm_serial_servo_write6_array(RESET_POSITION, 1200)
        time.sleep(1.5)
        
        self.arm.Arm_serial_servo_write6_array(RESET_POSITION, 800)
        time.sleep(1.0)
        
        for servo_id in range(1, 7):
            self._write_servo_angle(servo_id, RESET_POSITION[servo_id-1], 500)
        
        self.arm.Arm_serial_servo_write6_array(RESET_POSITION, 500)
        time.sleep(0.6)
        
        self.current_angles = RESET_POSITION.copy()
        return "✅ 机械臂已成功复位"
    
    # 增大手臂下弯步长（保留）
    def base_left(self, step=10):
        new_angle = self._clamp_angle(1, self.current_angles[0] - step)
        if self._write_servo_angle(1, new_angle, 300):
            return f"底座左转 → {new_angle}°"
        return "底座左转失败"
    
    def base_right(self, step=10):
        new_angle = self._clamp_angle(1, self.current_angles[0] + step)
        if self._write_servo_angle(1, new_angle, 300):
            return f"底座右转 → {new_angle}°"
        return "底座右转失败"
    
    def arm_up(self, step=20):
        shoulder_angle = self._clamp_angle(2, self.current_angles[1] - step)
        elbow_angle = self._clamp_angle(3, self.current_angles[2] + step)
        
        success1 = self._write_servo_angle(2, shoulder_angle, 500)
        success2 = self._write_servo_angle(3, elbow_angle, 500)
        
        if success1 and success2:
            return f"手臂抬起 → 大臂{shoulder_angle}° 小臂{elbow_angle}°"
        return "手臂抬起失败"
    
    def arm_down(self, step=20):
        shoulder_angle = self._clamp_angle(2, self.current_angles[1] + step)
        elbow_angle = self._clamp_angle(3, self.current_angles[2] - step)
        
        success1 = self._write_servo_angle(2, shoulder_angle, 500)
        success2 = self._write_servo_angle(3, elbow_angle, 500)
        
        if success1 and success2:
            return f"手臂下弯 → 大臂{shoulder_angle}° 小臂{elbow_angle}°"
        return "手臂下弯失败"
    
    # 一键到夹取位置（保留）
    def go_to_pick_position(self):
        print("🔄 正在移动到地面夹取位置...")
        
        self._write_servo_angle(6, SAFE_LIMITS[6][0], 300)
        time.sleep(0.3)
        
        self._write_servo_angle(2, PICK_POSITION[1], 800)
        self._write_servo_angle(3, PICK_POSITION[2], 800)
        time.sleep(1.0)
        
        self._write_servo_angle(4, PICK_POSITION[3], 300)
        time.sleep(0.3)
        
        self.current_angles[1] = PICK_POSITION[1]
        self.current_angles[2] = PICK_POSITION[2]
        self.current_angles[3] = PICK_POSITION[3]
        
        return "✅ 已到达地面夹取位置"
    
    def gripper_open(self):
        if self._write_servo_angle(6, SAFE_LIMITS[6][0], 300):
            return "✅ 夹爪已张开"
        return "夹爪张开失败"
    
    def gripper_close(self):
        if self._write_servo_angle(6, SAFE_LIMITS[6][1], 300):
            return "✅ 夹爪已闭合"
        return "夹爪闭合失败"
    
    def process_command(self, command):
        command = command.strip().upper()
        print(f"\n收到指令: {command}")
        
        try:
            # 解析滑块绝对角度指令（保留）
            if ":" in command:
                parts = command.split(":")
                servo_id = int(parts[0][1:])
                angle = int(parts[1])
                return self.set_servo_absolute(servo_id, angle)
            
            # 原有指令（完全保留）
            if command == "BASE_LEFT":
                return self.base_left()
            elif command == "BASE_RIGHT":
                return self.base_right()
            elif command == "ARM_UP":
                return self.arm_up()
            elif command == "ARM_DOWN":
                return self.arm_down()
            elif command == "GRIPPER_OPEN":
                return self.gripper_open()
            elif command == "GRIPPER_CLOSE":
                return self.gripper_close()
            elif command == "RESET":
                return self.force_reset()
            elif command == "PICK_POSITION":
                return self.go_to_pick_position()
            elif command == "STATUS":
                angles = [f"{i+1}:{a}°" for i, a in enumerate(self.current_angles)]
                return f"当前角度: {', '.join(angles)}"
            elif command == "S1+": return self.adjust_single_servo(1, 5)
            elif command == "S1-": return self.adjust_single_servo(1, -5)
            elif command == "S2+": return self.adjust_single_servo(2, 5)
            elif command == "S2-": return self.adjust_single_servo(2, -5)
            elif command == "S3+": return self.adjust_single_servo(3, 5)
            elif command == "S3-": return self.adjust_single_servo(3, -5)
            elif command == "S4+": return self.adjust_single_servo(4, 5)
            elif command == "S4-": return self.adjust_single_servo(4, -5)
            elif command == "S5+": return self.adjust_single_servo(5, 5)
            elif command == "S5-": return self.adjust_single_servo(5, -5)
            elif command == "S6+": return self.adjust_single_servo(6, 5)
            elif command == "S6-": return self.adjust_single_servo(6, -5)
            else:
                return f"❌ 未知指令: {command}"
                
        except Exception as e:
            return f"❌ 执行错误: {str(e)}"
    
    def shutdown(self):
        print("\n🔄 正在安全关闭...")
        self.running = False
        self.force_reset()
        print("✅ 已安全关闭，机械臂已复位")

# ====================== 新增：WiFi更换后获取所有可用IP ======================
def get_all_raspberrypi_ips():
    """获取树莓派所有网卡的IP地址（WiFi/以太网）"""
    ips = []
    try:
        # 获取所有网卡
        interfaces = netifaces.interfaces()
        for iface in interfaces:
            # 跳过回环地址
            if iface == "lo":
                continue
            # 获取IPv4地址
            addrs = netifaces.ifaddresses(iface).get(netifaces.AF_INET, [])
            for addr in addrs:
                ip = addr.get("addr")
                if ip and not ip.startswith("127."):
                    ips.append((iface, ip))
    except Exception as e:
        print(f"⚠️ 获取IP失败: {e}")
    
    # 兼容旧方法
    if not ips:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            ips.append(("default", ip))
        except:
            ips.append(("default", "127.0.0.1"))
    
    return ips

# ====================== TCP服务器（保留所有旧代码 + 新增多IP显示） ======================
def main():
    controller = None
    server_socket = None
    
    try:
        controller = DofbotGestureController()
        
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        server_socket.settimeout(1.0)
        
        HOST = "0.0.0.0"
        PORT = 9500
        
        server_socket.bind((HOST, PORT))
        server_socket.listen(1)
        
        # 新增：显示所有可用IP
        all_ips = get_all_raspberrypi_ips()
        print(f"\n✅ TCP服务器已启动")
        print(f"监听地址: {HOST}:{PORT}")
        print("🌐 树莓派所有可用IP（WiFi更换后选择对应IP）:")
        for iface, ip in all_ips:
            print(f"   - {iface}: {ip}")
        print("💡 新增功能: 发送PICK_POSITION指令一键到地面夹取位置")
        print("💡 新增功能: 滑动摇杆绝对角度控制")
        print("等待Apple Vision Pro连接...")
        
        while True:
            try:
                client_socket, client_address = server_socket.accept()
                print(f"\n✅ 客户端已连接: {client_address}")
                
                try:
                    while True:
                        data = client_socket.recv(1024)
                        if not data:
                            break
                        
                        response = controller.process_command(data.decode('utf-8'))
                        print(f"执行结果: {response}")
                        
                        client_socket.sendall(response.encode('utf-8'))
                        
                except Exception as e:
                    print(f"客户端连接错误: {str(e)}")
                finally:
                    client_socket.close()
                    print("客户端已断开连接")
            except socket.timeout:
                continue
                
    except KeyboardInterrupt:
        print("\n\n用户中断程序")
    finally:
        if server_socket is not None:
            server_socket.close()
        if controller is not None:
            controller.shutdown()

if __name__ == "__main__":
    main()
