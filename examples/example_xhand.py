#!/usr/bin/env python3
"""
Simple script to playback a recorded trajectory from recording_traj.json
"""

from xhand_controller import xhand_control
import json
import time
import sys
import numpy as np
from pynput import keyboard as pkb


def interpolate_trajectory(trajectory, num_frames=100):
    """
    Interpolate trajectory from 7 waypoints to num_frames using linear interpolation.
    
    Args:
        trajectory: list of waypoints, shape (7, 12)
        num_frames: number of frames to interpolate to (default: 100)
    
    Returns:
        numpy array of shape (num_frames, 12)
    """
    traj_array = np.array(trajectory)  # Shape: (7, 12)
    n_waypoints, n_fingers = traj_array.shape
    
    # Create interpolation indices
    old_indices = np.linspace(0, 1, n_waypoints)  # [0, 1/6, 2/6, ..., 1]
    new_indices = np.linspace(0, 1, num_frames)   # [0, 1/99, 2/99, ..., 1]
    
    # Interpolate each finger
    interpolated = np.zeros((num_frames, n_fingers))
    for finger_idx in range(n_fingers):
        interpolated[:, finger_idx] = np.interp(new_indices, old_indices, traj_array[:, finger_idx])
    
    return interpolated


def main():
    ############################################
    # Initialize the XHand controller
    ############################################
    print("Initializing XHand controller...")
    device = xhand_control.XHandControl()
    hand_command = xhand_control.HandCommand_t()
    
    # Configure default command parameters
    for i in range(12):
        hand_command.finger_command[i].id = i
        hand_command.finger_command[i].kp = 150
        hand_command.finger_command[i].ki = 20
        hand_command.finger_command[i].kd = 40
        hand_command.finger_command[i].tor_max = 300
        hand_command.finger_command[i].mode = 3  # Position mode
    
    # Open RS485 connection
    print("Opening RS485 connection...")
    serial_port = '/dev/ttyUSB0'
    baud_rate = 3000000
    
    rsp = device.open_serial(serial_port, baud_rate)
    if rsp.error_code != 0:
        print(f"Error opening device: {rsp.error_message}")
        print("Please check serial_port and connection")
        sys.exit(1)
    
    print(f"Successfully opened {serial_port}")
    
    # Get hand ID
    hand_id_list = device.list_hands_id()
    if not hand_id_list:
        print("No hand devices found!")
        sys.exit(1)
    
    hand_id = hand_id_list[0]
    print(f"Found hand with ID: {hand_id}")

    ############################################
    # Load trajectory from JSON file
    ############################################
    print("\nLoading trajectory from assets/xhand/control_seq.json...")
    try:
        with open('assets/xhand/control_seq.json', 'r') as f:
            data = json.load(f)
            trajectory = np.array(data['trajectory'])

            #############################################
            # Modify trajectory to fit the hand's calibration
            # Add offset or scale factor to the trajectory
            # trajectory is of shape (num_waypoints, num_dof)
            #############################################

            trajectory[:, 0] = trajectory[:, 0] - 0.025
            # Example:
            # trajectory[:, 1] = trajectory[:, 1] + 0.025
            # trajectory[:, 2] = trajectory[:, 2] + 0.05

    except FileNotFoundError:
        print("Error: recording_traj.json not found!")
        sys.exit(1)
    except Exception as e:
        print(f"Error loading trajectory: {e}")
        sys.exit(1)
    
    print(f"Loaded trajectory with {len(trajectory)} waypoints")
    print(f"Each waypoint has {len(trajectory[0])} finger positions")
    
    # Interpolate trajectory to 100 frames
    print("\nInterpolating trajectory to 100 frames...")
    interpolated_traj = interpolate_trajectory(trajectory, num_frames=100)
    print(f"Interpolated trajectory shape: {interpolated_traj.shape}")

    ############################################
    # Set up keyboard control & Execute the trajectory
    ############################################
    # t parameter: 0.0 to 1.0 maps to full trajectory
    t = 0.0
    HOTKEYS = ("z", "x", "q")
    KEY_STATE = dict.fromkeys(HOTKEYS, False)
    
    def on_press(key):
        if (c := getattr(key, "char", None)) in KEY_STATE:
            KEY_STATE[c] = True
    
    def on_release(key):
        if (c := getattr(key, "char", None)) in KEY_STATE:
            KEY_STATE[c] = False
    
    # Start keyboard listener
    listener = pkb.Listener(on_press=on_press, on_release=on_release)
    listener.start()
    
    print("\n" + "="*60)
    print("Keyboard Control:")
    print("  z - Close hand (increase t by 0.05)")
    print("  x - Open hand (decrease t by 0.05)")
    print("  q - Quit")
    print("  t parameter: 0.0 (start) to 1.0 (end)")
    print("="*60 + "\n")
    
    # Control loop
    try:
        while True:
            # Update t based on key state
            if KEY_STATE["z"]:
                t = min(1.0, t + 0.05)
                print(f"z pressed: t = {t:.3f}")
            elif KEY_STATE["x"]:
                t = max(0.0, t - 0.05)
                print(f"x pressed: t = {t:.3f}")
            elif KEY_STATE["q"]:
                print("Quitting...")
                break
            
            # Map t (0 to 1) to frame index (0 to 99)
            frame_idx = int(t * 99)
            positions = interpolated_traj[frame_idx]
            
            # Set finger positions
            for finger_idx in range(12):
                hand_command.finger_command[finger_idx].position = positions[finger_idx]
            
            # Send command to hand
            error_struct = device.send_command(hand_id, hand_command)
            if error_struct.error_code != 0:
                print(f"Error: {error_struct.error_message}")
            
            time.sleep(0.05)  # 20Hz update rate
            
    except KeyboardInterrupt:
        print("\nInterrupted by user")
    finally:
        listener.stop()
        print("Closing device...")
        print("Done!")

if __name__ == "__main__":
    main()

