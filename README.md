# Base System — How it works (FRA263 / FRA264)

This document describes the **Base System** application that runs on the PC: what it connects to, **how data moves**, and **what each Modbus register address means**. You use the program as provided; you do not need its internal source code to follow this guide.
<!-- 
For step-by-step connection checks and example messages, see **[`test.md`](test.md)**. -->

---


## Prerequisites

Before starting the installation, ensure you have the following software installed:

* **Docker Desktop:** [Download here](https://www.docker.com)
* **Python 3.x:** For running the Backend Server.
* **Pip:** Python package manager.
* Install python package (Recomended to use venv)
```bash
pip install -r requirements.txt
```

---

## Installation Steps

Follow these steps to deploy both the Frontend and Backend services with a single command:

### 1. Prepare Your Files
Ensure the following 3 files are located in the same directory:
1.  `frontend-image.tar` (The Web UI Image)
2.  `docker-compose.yml` (The configuration file start the interface)
3. `main.exe` (For connect to STM)

### 2. Load Docker Images
Open your Terminal or Command Prompt in that directory and run:
```bash
docker load -i frontend-image.tar
```

### 3. Start the System

1. Launch the entire stack using Docker Compose:
```bash
docker-compose up -d
```
<!-- Status: Once the terminal shows Started, the dashboard will be live at: http://localhost:3000 -->

2. Start the python server
```bash
run the main.exe
```

Once `server.py` is running, your terminal should display:
`WebSocket Server is running on ws://localhost:8765...`

1.  Open your web browser.
2.  Navigate to: **[http://localhost:3000](http://localhost:3000)** (Reload once if it shown disconnect from python, If not work check if main is running)

---

### How to Stop and Remove the Container
If you need to stop the system or clean up the container, use these commands:

* Stops and removes all containers and networks.
    ```bash
    docker-compose down
    ```
* Verifies if both Frontend and Backend are currently running.
    ```bash
    docker-compose ps
    ```
* View error messages or activity from the Python Backend.
    ```bash
    docker-compose logs backend
    ```
* Restarts all containers without deleting them.
    ```bash
    docker-compose restart
    ```
---
## How to use 

- **[How to use Basesystem 101](https://canva.link/9pr3jhzbh18pxbn)**


---

<!-- > [!TIP]
> Use `docker ps -a` to check the status of all your containers.
 -->

> [!IMPORTANT]
> Ensure that port **3000** (Web UI) and port **8765** (WebSocket) are not being used by other applications.

---




## 1. What the Base System does (big picture)

1. You use the **web user interface (UI)** in the browser.
2. The UI talks to the Base System over a **local WebSocket** (JSON messages on your PC).
3. The Base System talks to the **robot controller (STM32)** over **USB serial** using **Modbus RTU**.
4. Each side only sees its own link: the UI never speaks Modbus directly; the robot never sees the WebSocket.


**Serial link (Modbus RTU)** — must match the robot firmware:

| Setting   | Value   |
|----------|---------|
| Baud     | 19200   |
| Data bits| 8       |
| Parity   | Even    |
| Stop bits| 1       |

**Modbus slave address:** default **21** 

---

## 2. How data is **sent** and **received**

### 2.1 From PC to robot (**WRITE**)

The Base System sends **Write Single Register** commands. Each write targets **one 16-bit holding register** at a time, identified by its **address** (hex below).

- Some registers carry **bit patterns** (mode flags, gripper command codes).
- Others carry **signed numbers** (−32768 … +32767). On the wire, negative values are sent as **16-bit two’s complement** (the same integer range, encoded as 0…65535).

### 2.1.1 Registers that are mainly “one bit active”

Every holding register is still **16 bits** on the wire. For many **control** and **status** addresses, the firmware only defines **low bits** (often **bit 0** only, or bits **0–4**). The tables below add **decimal**, **hex**, and **binary (low bits)**.

<!-- - **WRITE:** e.g. **0x01** (mode) uses **one** power-of-two at a time -> exactly **one** bit set among bits 0–4. **0x04, 0x06, 0x23, 0x25** use **bit 0** as on/off or choice.
- **READ:** e.g. **0x26–0x27, 0x31** — each listed bit is **1 = active**, **0 = inactive** (unless the lab states otherwise). -->

Full **int16** magnitudes (jog, P2P value, test speeds, **0x28–0x30**) are **not** “one-hot bits”; use decimal / two’s complement for those.

### 2.2 From robot to PC (**READ**)

The Base System periodically **reads a block** of holding registers starting at address **0x00**, through **0x31** (50 registers in one read). That gives:

- **Heartbeat** value on **0x00**
- **Status** on **0x26 … 0x31** (sensors, task, motion, emergency)

The UI is updated from these read values (position, speed, gripper state, etc.).

### 2.3 Heartbeat (special case on **0x00**)

| Who   | Action |
|-------|--------|
| Robot | Writes **22881** (“YA”) into register **0x00** when it expects a reply. |
| Base System | Writes **18537** (“HI”) back into **0x00**. |

If the Base System does not see the expected heartbeat pattern in time, the UI can show the link as **not alive**, even if the cable is plugged in.

### 2.4 Numbers with a decimal place (position, speed, acceleration)

For **READ** addresses **0x28, 0x29, 0x30**, the register holds a **signed integer** that is **10×** the real value:

| Meaning        | Register | Decode |
|----------------|----------|--------|
| Real position  | 0x28     | `real = (signed raw) / 10` |
| Real velocity  | 0x29     | same |
| Real acceleration | 0x30  | same |

**Example:** if the read raw value is **1234**, the Base System shows **123.4** for that quantity.

---

## 3. WRITE register map — commands the PC sends to the robot

Every row is something the Base System can **write** when you use the UI. Addresses are **hexadecimal**.

### 3.1 Summary table (all write addresses)

| Addr | Topic | Short description |
|-----:|--------|-------------------|
| **0x00** | Heartbeat | Reply **HI (18537)** when robot sends **YA (22881)** on read. |
| **0x01** | Operating mode | Select Home / Jog / Auto / Set home / Test (one flag value at a time). |
| **0x02** | Manual gripper motion | Up, Down, Open, Close (encoded values below). |
| **0x03** | Gripper sequence | Pick or Place. |
| **0x04** | Gripper in AUTO | Enable or disable gripper actions during automatic motion. |
| **0x05** | Jog | Signed step size in **degrees** (+ = CCW, − = CW). |
| **0x06** | Test type | Performance vs Precision test. |
| **0x07** | Performance test | Desired velocity. |
| **0x08** | Performance test | Desired acceleration. |
| **0x09** | Precision test | Initial position. |
| **0x10** | Precision test | Final (target) position. |
| **0x11** | Precision test | Repeat count; **sign** selects **unit** (degree vs index — see 3.6). |
| **0x12 – 0x21** | Pick & place | Sequence slots: hole index and direction per slot (signed int16). |
| **0x22** | Pick & place | Number of **pairs** (pick+place) in the sequence. |
| **0x23** | Point-to-point | Unit: **degree** or **saved index**. |
| **0x24** | Point-to-point | Target value (signed), interpreted using **0x23**. |
| **0x25** | Safety | Soft stop: run vs stop. |

---

### 3.2 **0x01** — Operating mode (single bit “on” among bits 0–4)

The UI sends **one** value to **0x01**. Each value is a **power of two**: in binary, **exactly one** of the low bits is **1** (one-hot style for mode select).

| Bit | Mask (dec) | Mask (hex) | Low 5 bits (binary) | Mode / command |
|:---:|:----------:|:----------:|:-------------------:|----------------|
| **0** | **1** | 0x0001 | `0b00001` | Go home |
| **1** | **2** | 0x0002 | `0b00010` | Manual / Jog |
| **2** | **4** | 0x0004 | `0b00100` | Auto |
| **3** | **8** | 0x0008 | `0b01000` | Set home |
| **4** | **16** | 0x0010 | `0b10000` | Test |

The full register is 16 bits; bits **5–15** are **0** in normal use unless firmware defines more.

---

### 3.3 **0x02** — Gripper: Up / Down / Open / Close (manual)

Each command writes a **different code**; values **1, 2, 4** are **single-bit masks** in bits 0–2 (**Up** is all bits clear in that group).

| Command | Dec | Hex | Low 4 bits (binary) | Note |
|---------|----:|----:|:-------------------:|------|
| Up      | **0** | 0x0000 | `0b0000` | No command bits set |
| Down    | **1** | 0x0001 | `0b0001` | **bit 0** |
| Open    | **2** | 0x0002 | `0b0010` | **bit 1** |
| Close   | **4** | 0x0004 | `0b0100` | **bit 2** |

---

### 3.4 **0x03** — Gripper: Pick / Place

| Command | Dec | Hex | Low 2 bits (binary) | Active bit |
|---------|----:|----:|:-------------------:|:----------:|
| Pick    | **1** | 0x0001 | `0b01` | **bit 0** |
| Place   | **2** | 0x0002 | `0b10` | **bit 1** |

---

### 3.5 **0x04** — Gripper enable (used with AUTO)

Only **bit 0** is used as enable; rest of the register is **0** in normal use.

| Dec | Hex | Binary (low 4) | **bit 0** | Meaning |
|----:|----:|:--------------:|:---------:|---------|
| **0** | 0x0000 | `0b0000` | **0** | Gripper **disabled** during auto |
| **1** | 0x0001 | `0b0001` | **1** | Gripper **enabled** during auto |

---

### 3.6 **0x05** — Jog (degrees)

| Content | Type | Meaning |
|---------|------|---------|
| Signed int16 | degrees step | **Positive** -> counter-clockwise (CCW). **Negative** -> clockwise (CW). |

---

### 3.7 **0x06 – 0x11** — Test modes

| Addr | Name | Value / type | Meaning |
|-----:|------|----------------|----------|
| **0x06** | Test mode | **0** / **1** (see bit table below) | Precision vs Performance |
| **0x07** | Performance | Signed int16 | Desired **velocity** |
| **0x08** | Performance | Signed int16 | Desired **acceleration** |
| **0x09** | Precision | Signed int16 | **Initial** position |
| **0x10** | Precision | Signed int16 | **Final** position |
| **0x11** | Precision | Signed int16 | **Repetition count**; **sign** encodes **unit** for repeats (positive -> degree vs negative -> index)  |

**0x06 — binary (test type, bit 0 only):**

| Dec | Hex | Low 2 bits | **bit 0** | Meaning |
|----:|----:|:----------:|:---------:|---------|
| **0** | 0x0000 | `0b0` | **0** | Precision test |
| **1** | 0x0001 | `0b1` | **1** | Performance test |

---

### 3.8 **0x12 – 0x21** — Pick and place sequence

There are **10 consecutive addresses** (**0x12** through **0x21**). Each holds **one signed 16-bit value** for one step of the programmed sequence.

| Concept | Rule |
|---------|------|
| **Magnitude** | Hole **index** (e.g. 1…5). |
| **Sign** | **+** -> counter-clockwise, **−** -> clockwise.|

The Base System fills these from your pick/place plan in the UI, then writes **0x22**.

---

### 3.9 **0x22** — Number of pick–place pairs

| Content | Meaning |
|---------|---------|
| Unsigned count | How many **pairs** (pick + place) the sequence contains. |

---

### 3.10 **0x23** — Point-to-point: unit

Only **bit 0** selects the unit; **0** = degree, **1** = index.

| Dec | Hex | Low 2 bits | **bit 0** | Unit for **0x24** |
|----:|----:|:----------:|:---------:|-------------------|
| **0** | 0x0000 | `0b0` | **0** | **Degree** |
| **1** | 0x0001 | `0b1` | **1** | **Index**  |

---

### 3.11 **0x24** — Point-to-point: target

| Content | Meaning |
|---------|---------|
| Signed int16 | Target **degrees** or **index**, depending on **0x23**. Sign indicates direction where the motion planner uses it. |

---

### 3.12 **0x25** — Soft stop

| Dec | Hex | Low 2 bits | **bit 0** | Meaning |
|----:|----:|:----------:|:---------:|---------|
| **0** | 0x0000 | `0b0` | **0** | Normal running |
| **1** | 0x0001 | `0b1` | **1** | Request **soft stop** |

---

## 4. READ register map — status the robot sends to the PC

The Base System **reads** these to refresh the UI. Block read covers **0x00** and **0x26 … 0x31**.

### 4.1 Summary table

| Addr | Name | What you use it for |
|-----:|------|---------------------|
| **0x00** | Heartbeat | Link life; robot sends **YA (22881)**; PC answers **HI** on write. |
| **0x26** | Lead / reed sensors | Physical gripper limits and jaw state (bits). |
| **0x27** | Current task | What the motion sequencer is doing (Homing, Pick, Place, etc.). |
| **0x28** | Position | θ position vs current home (**÷ 10** for display). |
| **0x29** | Velocity | **÷ 10** for display. |
| **0x30** | Acceleration | **÷ 10** for display. |
| **0x31** | Emergency | Emergency input / safety state (bit). |

---

### 4.2 **0x26** — Lead / reed sensors (typical bit meaning)

Low bits of the register describe **three reed switches** (on/off). The Base System derives gripper **height** and **jaw** labels for the UI.

| Bit | Mask (hex) | Weight | Binary place | **1 =** | Meaning (hardware) |
|:---:|:----------:|:------:|:------------:|---------|---------------------|
| **0** | 0x0001 | 1 | `...0001` | Reed 1 **ON** | Often paired with bit 1 for **up/down** |
| **1** | 0x0002 | 2 | `...0010` | Reed 2 **ON** | |
| **2** | 0x0004 | 4 | `...0100` | Reed 3 **ON** | Often **jaw closed** when active |

**Example raw value:** if **only** bits 0 and 2 are high -> `0b0101` -> dec **5** (0x0005). Compare to what you read on the bus after masking the low 4 bits.

**Typical interpretation (when bits are wired as in the lab):**

| Reed 1 | Reed 2 | UI show |
|:------:|:------:|-------------|
| ON | OFF | Up |
| OFF | ON | Down |
| other | other | Idle / between |

| Reed 3 | UI show |
|:------:|----------------|
| ON | Closed |
| OFF | Open |

<!-- Exact wiring is defined on the robot; the **register** is always **0x26**. -->

---

### 4.3 **0x27** — Current robot task 

The Base System reads low bits and picks **one** task name (first match in this order). Each row is **“this bit = 1”** (other bits may be 0 or 1 depending on firmware; priority order is as implemented in the Base System).

| Bit | Mask (hex) | Mask (dec) | Low 4 bits (example **only** this bit) | Shown task |
|:---:|:----------:|:----------:|:---------------------------------------:|------------|
| **0** | 0x0001 | 1 | `0b0001` | Homing |
| **1** | 0x0002 | 2 | `0b0010` | Go Pick |
| **2** | 0x0004 | 4 | `0b0100` | Go Place |
| **3** | 0x0008 | 8 | `0b1000` | Go Point |
| — | — | **0** | `0b0000` | Idle (if none of the above match) |

---

### 4.4 **0x28, 0x29, 0x30** — Motion feedback (scaled ×10)

| Addr   | Quantity | Decode |
|--------|----------|--------|
| **0x28** | Position | signed raw **÷ 10** = user units |
| **0x29** | Velocity | signed raw **÷ 10** |
| **0x30** | Acceleration | signed raw **÷ 10** |

---

### 4.5 **0x31** — Emergency / safety state

Typically only **bit 0** is defined; treat **1** as “active / latched” per lab.

| Dec (if only bit0 matters) | Hex | Low 2 bits | **bit 0** | Meaning |
|---------------------------:|----:|:----------:|:---------:|---------|
| **0** | 0x0000 | `0b0` | **0** | Not in emergency (normal) |
| **1** | 0x0001 | `0b1` | **1** | Emergency active (e.g. E-stop / interlock — per firmware) |

---

## 5. Two’s complement (for signed registers)

If you read or write a **signed** value as a raw 16-bit number:

| If raw ≥ 32768 | Signed value = raw − 65536 |
|----------------|----------------------------|
| Else           | Signed value = raw |

**Example:** raw **65413** -> signed **−123**. After **÷ 10** on 0x28–0x30, that is **−12.3** in display units.

---

## 6. Windows: which COM port to choose

1. Open **Device Manager** -> **Ports (COM & LPT)**.
2. Find **STMicroelectronics STLink Virtual COM Port (COMx)**.
3. In the Base System connect dialog, enter that **COM** number (**x**).

---
  