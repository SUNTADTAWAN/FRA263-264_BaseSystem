# server.py
import asyncio
import json
import websockets
from websockets.exceptions import ConnectionClosed
from protocol import Protocol
import time

# Modbus Protocol
protocol = Protocol()

# Server state
server_state = {
    "stats_task": None,   
}

# Robot stats
robot_state = {
    "position": "--",
    "speed": "--",
    "accel": "--",
    "gripper_z": "Idle",
    "gripper_jaw": "Idle",
    "mode": "Idle",
    "emergency": "Idle",
}

HB_DEAD_TIMEOUT = 0.8   
HB_HI = 18537       # HI 
HB_YA = 22881       # YA

modbus_lock = asyncio.Lock()

async def stats_loop(websocket):
    last_seen_ya_time = 0.0
    try:
        while True:
            ok = False

            if protocol.client and protocol.is_connected():
                async with modbus_lock:
                    # ONE READ for everything
                    ok = await asyncio.to_thread(protocol.routine)

                    if ok:
                        hb_val = protocol.hb_val
                        if hb_val == HB_YA:
                            last_seen_ya_time = time.perf_counter()
                            sent_hi, _ = await asyncio.to_thread(protocol.heartbeat_from_routine)
                        
                        # print(protocol.register.registers)
                        # print(protocol.register.registers[0x30:0x36])
                        robot_state["position"] = protocol.theta_actual_pos
                        robot_state["speed"] = protocol.theta_actual_speed
                        robot_state["accel"] = protocol.theta_actual_accel
                        robot_state["emergency"] = protocol.emergency_stop_status
                        robot_state["mode"] = protocol.moving_status

                        # Check state gripper [0x04]
                        reed1 = protocol.gripper_actual_reed1
                        reed2 = protocol.gripper_actual_reed2
                        reed3 = protocol.gripper_actual_reed3

                        # gripper Z direction 
                        robot_state["gripper_z"] = (
                            "Up" if (reed1 and not reed2) else
                            "Down" if (reed2 and not reed1) else
                            "Idle"
                        )

                        # gripper jaw
                        if reed3 is True:
                            robot_state["gripper_jaw"] = "Close"
                        elif reed3 is False:
                            robot_state["gripper_jaw"] = "Open"
                        else:
                            robot_state["gripper_jaw"] = "Idle"
            
            # Check heartbeat are Normal
            dt = time.perf_counter() - last_seen_ya_time
            alive = dt <= HB_DEAD_TIMEOUT
            connected = bool(protocol.client) and protocol.is_connected() and alive

            # print()
            payload = {
                "type": "STATS",
                "pos": robot_state["position"],
                "speed": robot_state["speed"],
                "accel": robot_state["accel"],
                "gripper": f"{robot_state['gripper_z']} / {robot_state['gripper_jaw']}",
                "mode": robot_state["mode"],
                "emergency": robot_state["emergency"],
                # "connected": connected,
                "heartbeat": connected 
            }

            try:
                await websocket.send(json.dumps(payload))
            except ConnectionClosed:
                break
            # await asyncio.sleep(HB_PERIOD)
    except asyncio.CancelledError:
        pass

async def handler(websocket: websockets.WebSocketServerProtocol):
    print("React Client Connected!")

    # Ensure only ONE stats loop is active (React dev mode can connect twice)
    old = server_state.get("stats_task")
    if old and not old.done():
        old.cancel()
        try:
            await old
        except asyncio.CancelledError:
            pass

    stats_task = asyncio.create_task(stats_loop(websocket))
    server_state["stats_task"] = stats_task

    initial_stats = {
        "type": "STATS",
        "message": "Connected to Python Backend",
        "pos": robot_state["position"],
        "speed": robot_state["speed"],
        "accel": robot_state["accel"],
        "gripper": f"{robot_state['gripper_z']} / {robot_state['gripper_jaw']}",
        "mode": robot_state["mode"],
        "emergency": robot_state["emergency"],
        "connected": bool(protocol.client) and protocol.is_connected(),
    }

    try:
        await websocket.send(json.dumps(initial_stats))
    except ConnectionClosed:
        stats_task.cancel()
        return

    try:
        async for message in websocket:
            try:
                data = json.loads(message)
            except json.JSONDecodeError:
                await websocket.send(json.dumps({"mode": "Error", "message": "Invalid JSON"}))
                continue

            req_mode = data.get("mode")
            action = data.get("action")
            # ---------------- CONNECT / DISCONNECT ----------------
            if req_mode == "Connect" and action == "connect_port":
                port_num = data.get("port")
                com_port = f"COM{port_num}"
                slave = int(data.get("slave", 21))
                async with modbus_lock:
                    if protocol.client and protocol.is_connected() and protocol.port == com_port and protocol.slave_address == slave:
                        ok = True
                    else :
                        ok = await asyncio.to_thread(protocol.connect_rtu, com_port, slave)

                await websocket.send(json.dumps({
                    "mode": "Connect",
                    "action": "connect_port",
                    "status": "success" if ok else "failed",
                    "message": f"Connected to {com_port} (slave {slave})" if ok else f"Failed to connect to {com_port}",
                }))
                continue

            # ---------------- HOME ----------------
            if req_mode == "Home":
                if action == "go_home": # 0x01
                    async with modbus_lock:
                        await asyncio.to_thread(protocol.write_base_system_status, "go_home")
                    continue

                elif action == "set_home": #0x01
                    async with modbus_lock:
                        await asyncio.to_thread(protocol.write_base_system_status, "set_home")
                    continue

            # ---------------- MANUAL / JOG ----------------
            elif req_mode == "Manual":
                if action == "set_manual":  # 0x01
                    print(55555)
                    async with modbus_lock:
                        await asyncio.to_thread(protocol.write_base_system_status, "Jog")
                    continue

                # 0x03
                elif action == "gripper_up":
                    async with modbus_lock:
                        await asyncio.to_thread(protocol.write_gripper_movement, "Up")
                    continue

                elif action == "gripper_down":
                    async with modbus_lock:
                        await asyncio.to_thread(protocol.write_gripper_movement, "Down")
                    continue

                # 0x02
                elif action == "gripper_open":
                    async with modbus_lock:
                        await asyncio.to_thread(protocol.write_gripper_command, "Open")
                    continue

                elif action == "gripper_close":
                    async with modbus_lock:
                        await asyncio.to_thread(protocol.write_gripper_command, "Close")
                    continue

                elif action == "gripper_pick":
                    async with modbus_lock:
                        await asyncio.to_thread(protocol.write_gripper_command, "Pick")
                    continue

                elif action == "gripper_place":
                    async with modbus_lock:
                        await asyncio.to_thread(protocol.write_gripper_command, "Place")
                    continue
                
                # 0x14
                elif action == 'jog':
                    value = data.get('value')
                    direction = '+' if data.get('direction') == 'CCW' else '-'
                    jog_value = int(str(direction) + str(value))
                    async with modbus_lock:
                        await asyncio.to_thread(protocol.write_jog, jog_value)
                    continue

            # ---------------- AUTO ----------------
            elif req_mode == "Auto":
                if action == 'set_auto':
                    async with modbus_lock:
                        await asyncio.to_thread(protocol.write_base_system_status, "Auto")
                    continue

                if action == "pick_place":
                    order_sequence = data.get('sequence')
                    direction_sequence = data.get('directions')
                    gripper_enable = (data.get('use_gripper'))   

                    if gripper_enable:  # 0x05
                        async with modbus_lock:
                            await asyncio.to_thread(protocol.write_gripper_checkbox, 'Enable')
                        continue

                    else:
                        async with modbus_lock:
                            await asyncio.to_thread(protocol.write_gripper_checkbox, 'Disable')
                        continue
                
                elif action == 'point_to_point':    
                    p2p_unit = data.get('unit')
                    p2p_value = data.get('value')
                    async with modbus_lock:
                        await asyncio.to_thread(protocol.write_p2p_unit, p2p_unit)      # 0x31
                        await asyncio.to_thread(protocol.write_p2p_value, p2p_value)    # 0x32
                    continue

            # ---------------- TEST ----------------
            elif req_mode == "Test":
                if action == "set_test":
                    async with modbus_lock:
                        await asyncio.to_thread(protocol.write_base_system_status, "Test")
                    continue

                elif action == "performance": 
                    speed_test = data.get('speed')
                    accel_test = data.get('accel')

                    async with modbus_lock:
                        await asyncio.to_thread(protocol.write_test_mode, 'Performance')    # 0x15
                        await asyncio.to_thread(protocol.write_test_speed, speed_test)      # 0x16
                        await asyncio.to_thread(protocol.write_test_accel, accel_test)      # 0x17
                    continue

                elif action == "precision":
                    init_pos_test = data.get('init_pos')
                    target_pos_test = data.get('tar_pos')
                    repeat_test = data.get('repeat')
                    unit_test = data.get('unit')
                    
                    unit_sign = '+' if unit_test == 'degree' else '-'
                    repeat_w_unit = int(str(unit_sign) + str(repeat_test))
                    async with modbus_lock:
                        await asyncio.to_thread(protocol.write_test_mode, 'Precision')      # 0x15
                        await asyncio.to_thread(protocol.write_test_init_pos, init_pos_test)        # 0x18
                        await asyncio.to_thread(protocol.write_test_target_pos, target_pos_test)    # 0x19
                        await asyncio.to_thread(protocol.write_test_repeat, repeat_w_unit)          # 0x20
                    continue

            # # ---------------- STOP ----------------
            elif req_mode == "Stop" and action == 'stop':
                async with modbus_lock:
                    await asyncio.to_thread(protocol.write_stop_process, 'Stop')    # 0x34
                continue

            else : 
                print(f"[ERROR] Can't recog{req_mode}")

            # ---------------- FALLBACK ----------------
            await websocket.send(json.dumps({
                "mode": "Error",
                "message": f"Unsupported command: mode={req_mode}, action={action}"
            }))

    except websockets.exceptions.ConnectionClosed:
        print("Frontend client disconnected.")
    finally:
        stats_task.cancel()
        try:
            await stats_task
        except asyncio.CancelledError:
            pass


async def main():
    async with websockets.serve(handler, "localhost", 8765):
        print("WebSocket Server running ws://localhost:8765")
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())