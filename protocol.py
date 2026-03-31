import platform 
from pymodbus.client import ModbusSerialClient as ModbusClient


MAX_ADDRESS = 0x34

HB_HI = 18537       # HI 
HB_YA = 22881       # YA

class Binary():
    """
    Binary Class
    """
    def decimal_to_binary(self, decimal_num):
        """
        This function converts base 10 to base 2
        """
        binary_num = ""
        while decimal_num > 0:
            binary_num = str(decimal_num % 2) + binary_num
            decimal_num = decimal_num // 2
        # Fill to 16 digits with 0
        if len(binary_num) < 16:
            binary_num = "0"*(16-len(binary_num)) + binary_num
        return binary_num
        
    def binary_to_decimal(self, binary_num):
        """
        This function converts base 2 to base 10
        """
        decimal_num = 0
        for i in range(len(binary_num)):
            decimal_num += int(binary_num[i]) * (2 ** (len(binary_num)-i-1))
        return decimal_num
    
    def binary_crop(self, digit, binary_num):
        """
        This function crops the last n digits of the binary number
        """
        return binary_num[len(binary_num)-digit:]

    def binary_twos_complement(self, number):
        """
        This functions converts the (negative) number to its 16-bit two's complement representation
        """
        if number < 0:
            number = (1 << 16) + number  # Adding 2^16 to the negative number
        return number
    
    def binary_reverse_twos_complement(self, number):
        """
        This functions converts the 16-bit two's complement number back to its original signed representation 
        """
        if number & (1 << 15):  # Check if the most significant bit is 1
            number = number - (1 << 16)  # Subtract 2^16 from the number
        return number


class Protocol(Binary):
    def __init__(self):
        self.port = None
        self.client = None

        # Modbus Client
        self.usb_connect = False
        self.slave_address = 21  # Modbus slave address
        self.register = None

        # Routine
        self.routine_normal = True

        # Heartbeat (0x00)
        self.hb_val = None

        # Base system status (0x01)
        self.base_system_status_register = 0b0000
        
        # Gripper status (0x02) -- 0: Release, 1: Grip
        self.gripper_status = "0"
        
        # Gripper Movement status (0x03) 0: Backward, 1: Forward
        self.gripper_moving_status = "0"

        # Gripper Movement Actual Status (0x04) 
        self.gripper_actual_reed1 = "0"  
        self.gripper_actual_reed2 = "0"
        self.gripper_actual_reed3 = "0"

        # Gripper Checkbox (0x05) -- 0: Disable, 1: Enable
        self.gripper_checkbox = "0"

        # Thetha Moving Status (0x10)
        self.moving_status = "Idle"
        self.moving_status_previous = "Idle"

        # Theta Moving Status (0x11 - 0x13) 
        self.theta_actual_pos = 0.0
        self.theta_actual_speed = 0.0
        self.theta_actual_accel = 0.0

        # Emergency Stop Status (0x40) -- 0: Normal, 1: Emergency Stop
        self.emergency_stop_status = "0" 

        # Stop the process (0x41) -- 0: Normal, 1: Stop
        self.stop_process = "0"

    def _write_register_debug(self, address: int, value: int, label: str = "") -> bool:
        """
        Generic FC06 write with full debug logging.
        """

        if not self.client:
            print(f"[ERROR] No Modbus client. Cannot write {label}")
            return False

        wr = self.client.write_register(
            address=address,
            value=value,
            slave=self.slave_address
        )

        ok = not (wr is None or (hasattr(wr, "isError") and wr.isError()))

        # Reverse two's complement for readable signed value
        signed_val = self.binary_reverse_twos_complement(value)

        print(
            f"[WRITE] {label:<20} | "
            f"Slave:{self.slave_address} | "
            f"Addr:{address} (0x{address:02X}) | "
            f"Raw:{value} | "
            f"Signed:{signed_val} | "
            f"Hex:0x{value:04X} | "
            f"Status:{'OK' if ok else 'ERROR'}"
        )

        return ok
    
    # ===== Connection Function ====== 
    def connect_rtu(self, com_port: str, slave: int = 21) -> bool:
            """Create + connect Modbus RTU client."""
            self.slave_address = slave
            self.port = com_port

            # close existing client if any
            self.disconnect()
            # print(com_port, slave)

            self.client = ModbusClient(
                port=com_port,
                baudrate=19200,
                parity="E",
                stopbits=1,
                bytesize=8,
                timeout=1,
                retries=1,
            )
            ok = self.client.connect()
            self.usb_connect = bool(ok)
            return bool(ok)

    def disconnect(self):
        if self.client:
            try:
                self.client.close()
            except Exception:
                pass
        self.client = None
        self.usb_connect = False

    def is_connected(self) -> bool:
        return bool(self.client) and bool(getattr(self.client, "connected", False))
    # ================================

    # === Routine Function ===
    def routine(self):
        if not self.client:
            self.routine_normal = False
            return False
        
        rr = self.client.read_holding_registers(address=0x00, count=MAX_ADDRESS+1, slave=self.slave_address)
        if rr is None or rr.isError() or not hasattr(rr, "registers"):
            self.routine_normal = False
            return False 

        self.register = rr

        # Heartbeat        
        self.hb_val = rr.registers[0]
        
        # Routine for reading registers
        self.read_gripper_actual_status()   # gripper status (0x02 - 0x04)
        self.read_theta_moving_status()     # theta moving status (0x10)
        self.read_theta_actual_status()     # theta actual status (0x11 - 0x13)
        self.read_emergency_stop_status()   # emergency stop status (0x33)
        self.routine_normal = True
        return True

    # === Heartbeat Functions (0x00) ===
    def write_heartbeat_hi(self) -> bool:
        wr = self.client.write_register(address=0x00, value=HB_HI, slave=self.slave_address)
        if wr is None or (hasattr(wr, "isError") and wr.isError()):
            return False
        return True

    # def write_heartbeat_hi(self) -> bool:
    #     return self._write_register_debug(0x00, HB_HI, "Heartbeat HI")
    
    def heartbeat_from_routine(self):
        hb = getattr(self, "hb_val", None)
        if hb is None:
            return False, None

        if hb == HB_YA:
            ok = self.write_heartbeat_hi()   # FC06 only
            return bool(ok), hb

        return False, hb
    
    # === Write Basesystem Mode (0x01) ===
    def write_base_system_status(self, command):
        if command == 'go_home':
            self.base_system_status_register = 0b0001   
        elif command == 'Jog':
            self.base_system_status_register = 0b0010
        elif command == 'Auto':
            self.base_system_status_register = 0b0100
        elif command == 'set_home':
            self.base_system_status_register = 0b1000
        elif command == 'Test':
            self.base_system_status_register = 0b10000

        # self.client.write_register(address=0x01, value=self.base_system_status_register, slave=self.slave_address)
        self._write_register_debug(0x01, self.base_system_status_register, f"BaseSystem {command}")

    # === Write Gripper action/sequence (0x02) ===
    def write_gripper_command(self, command):
        if command == 'Open':
            self.gripper_command_register = 0b0000   
        elif command == 'Close':
            self.gripper_command_register = 0b0001
        elif command == 'Pick':
            self.gripper_command_register = 0b0010
        elif command == 'Place':
            self.gripper_command_register = 0b0011
        # self.client.write_register(address=0x02, value=self.gripper_command_register, slave=self.slave_address)
        self._write_register_debug(0x02, self.gripper_command_register, f"Gripper {command}")

    # === Write Gripper Up/Down (0x03) ===
    def write_gripper_movement(self, command):
        if command == 'Up':
            self.gripper_movement_register = 0b0000   
        elif command == 'Down':
            self.gripper_movement_register = 0b0001
        # self.client.write_register(address=0x03, value=self.gripper_movement_register, slave=self.slave_address)
        self._write_register_debug(0x03, self.gripper_movement_register, f"GripperMove {command}")
    
    # === Read REED switch (0x04) ===
    def read_gripper_actual_status(self):
        # gripper_state_binary = self.binary_to_decimal(self.binary_crop(4, self.decimal_to_binary(self.register.registers[0x02])))
        # gripper_movement_binary = self.binary_crop(4, self.decimal_to_binary(self.register.registers[0x03]))[::-1]
        
        # Reed switch status
        gripper_actual_status_binary = self.binary_crop(4, self.decimal_to_binary(self.register.registers[0x04]))[::-1]
        self.gripper_actual_reed1 = (gripper_actual_status_binary[0] == '1') # Reed Switch 1 Status [0x04]
        self.gripper_actual_reed2 = (gripper_actual_status_binary[1] == '1') # Reed Switch 2 Status [0x04]
        self.gripper_actual_reed3 = (gripper_actual_status_binary[2] == '1') # Reed Switch 3 Status [0x04]

    # === Write Gripper Checkbox (AUTO mode) (0x05) ===
    def write_gripper_checkbox(self, command):
        if command == 'Disable':
            self.gripper_checkbox_register = 0b0000   
        elif command == 'Enable':
            self.gripper_checkbox_register = 0b0001
        # self.client.write_register(address=0x05, value=self.gripper_checkbox_register, slave=self.slave_address)
        self._write_register_debug(0x05, self.gripper_checkbox_register, f"GripperCheckbox {command}")
    
    # === Read Current robot states (0x10) ===
    def read_theta_moving_status(self):
        self.moving_status_previous = self.moving_status
        moving_status_binary = self.binary_crop(6, self.decimal_to_binary(self.register.registers[0x10]))[::-1]
        
        # moving_status_binary = ['0', '1', '0', '0']
        if moving_status_binary[0] == '1':
            self.moving_status = "Homing"
        elif moving_status_binary[1] == '1':
            self.moving_status = "Go Pick"
        elif moving_status_binary[2] == '1':
            self.moving_status = "Go Place"
        elif moving_status_binary[3] == '1':
            self.moving_status = "Go Point"
        else:
            self.moving_status = "Idle"

    # === Read Current pos,speed,acc (0x11 - 0x13) ===
    def read_theta_actual_status(self):
        # data must convert to 1 decimal point 
        # self.register.registers[0x11] = 64302 (-1234)
        # self.register.registers[0x12] = 1234 (1234)
        # self.register.registers[0x13] = 61215 (-4321)

        self.theta_actual_pos = self.binary_reverse_twos_complement(self.register.registers[0x11]) / 10.0
        self.theta_actual_speed = self.binary_reverse_twos_complement(self.register.registers[0x12]) / 10.0
        self.theta_actual_accel = self.binary_reverse_twos_complement(self.register.registers[0x13]) / 10.0

    # === Write Command (JOG mode) (0x14) ===
    def write_jog(self, value=None):
        self.jog_degree = self.binary_twos_complement(value)
        # self.client.write_register(address=0x14, value=self.jog_degree, slave=self.slave_address)
        self._write_register_debug(0x14, self.jog_degree, "JOG")

    # === Write Performance/Precision (TEST mode) (0x15) ===
    def write_test_mode(self, mode=None):
        if mode == "Performance":
            self.test_mode = 1
        elif mode == "Precision" :
            self.test_mode = 0 
        # self.client.write_register(address=0x15, value=self.test_mode, slave=self.slave_address)
        self._write_register_debug(0x15, self.test_mode, f"TestMode {mode}")

    # === Write Performance - speed (TEST mode) (0x16) ===
    def write_test_speed(self, value=None):
        self.test_speed = self.binary_twos_complement(value)
        # self.client.write_register(address=0x16, value=self.test_speed, slave=self.slave_address)
        self._write_register_debug(0x16, self.test_speed, "TestSpeed")

    # === Write Performance - accel (TEST mode) (0x17) ===
    def write_test_accel(self, value=None):
        self.test_accel = self.binary_twos_complement(value)
        # self.client.write_register(address=0x17, value=self.test_accel, slave=self.slave_address)
        self._write_register_debug(0x17, self.test_accel, "TestAccel")

    # === Write Precision - Init pos (TEST mode) (0x18) ===
    def write_test_init_pos(self, init_pos=None):
        self.test_init_pos = self.binary_twos_complement(init_pos)
        # self.client.write_register(address=0x18, value=self.test_init_pos, slave=self.slave_address)
        self._write_register_debug(0x18, self.test_init_pos, "TestInitPos")

    # === Write Precision - Target pos (TEST mode) (0x19) ===
    def write_test_target_pos(self, target_pos=None):
        self.test_target_pos = self.binary_twos_complement(target_pos)
        # self.client.write_register(address=0x19, value=self.test_target_pos, slave=self.slave_address)
        self._write_register_debug(0x19, self.test_target_pos, "TestTargetPos")

    # === Write Precision - #Repeat (sign = unit) (TEST mode) (0x20) ===
    def write_test_repeat(self, repeat=None):
        self.test_repeat_w_unit = self.binary_twos_complement(repeat)
        # self.client.write_register(address=0x20, value=self.test_repeat_w_unit, slave=self.slave_address)
        self._write_register_debug(0x20, self.test_repeat_w_unit, "TestRepeat")

    # === Write Pick Hole  #1-#5 (AUTO) (0x21 - 0x25) ===
    def write_pick_hole(self, pick_order, direction):
        pass
    # === Write Place Hole #1-#5 (AUTO) (0x26 - 0x30) ===
    def write_place_hole(self, place_order, direction):
        pass

    # === Write Point to Point (unit) (0x31) ===
    def write_p2p_unit(self, unit=None):
        if unit == 'degree':
            self.p2p_unit = 0b0000 
        elif unit == 'index':
            self.p2p_unit = 0b0001
        # self.client.write_register(address=0x31, value=self.p2p_unit, slave=self.slave_address)
        self._write_register_debug(0x31, self.p2p_unit, f"P2P Unit {unit}")

    # === Write Point to Point (value) (0x32) ===
    def write_p2p_value(self, value=None):
        self.p2p_value = self.binary_twos_complement(value)
        # self.client.write_register(address=0x32, value=self.p2p_value, slave=self.slave_address)
        self._write_register_debug(0x32, self.p2p_value, "P2P Value")

    # === Read Emergenct status (0x33) ===
    def read_emergency_stop_status(self):
        emergency_stop_binary = self.binary_crop(4, self.decimal_to_binary(self.register.registers[0x33]))[::-1]
        self.emergency_stop_status = (emergency_stop_binary[0] == '1')  # Emergency Stop Status

    # === Write Stop process (0x34) ===
    def write_stop_process(self, command):
        if command == 'Normal':
            self.stop_process_register = 0b0000   
        elif command == 'Stop':
            self.stop_process_register = 0b0001
        # self.client.write_register(address=0x34, value=self.stop_process_register, slave=self.slave_address)
        self._write_register_debug(0x34, self.stop_process_register, f"StopProcess {command}")