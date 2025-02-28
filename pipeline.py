import mido
from reapy import reascript_api as RPR
import os
import pyautogui
import time
import pygetwindow as gw

# Hardcoded paths
midi_dir = "C:/School/BP/Midi"
output_dir = "C:/School/BP/Wavs"
vsti_name = "Odin III"  # Replace with the name of your VSTi

# Check if the MIDI directory exists
if not os.path.exists(midi_dir):
    print(f"MIDI directory not found: {midi_dir}")
    exit()

# Check if the output directory exists, create if not
if not os.path.exists(output_dir):
    os.makedirs(output_dir)

# Create a new project
RPR.Main_OnCommand(40023, 0)  # New project

# Create a new track
RPR.Main_OnCommand(40001, 0)  # Insert new track

# Get the newly created track
track = RPR.GetTrack(0, 0)

# Add the VSTi to the track
fx_index = RPR.TrackFX_AddByName(track, vsti_name, False, -1)

# Function to shift MIDI notes up by one octave
def shift_midi_up_one_octave(midi_file_path, output_file_path):
    mid = mido.MidiFile(midi_file_path)
    for track in mid.tracks:
        for msg in track:
            if msg.type == 'note_on' or msg.type == 'note_off':
                msg.note += 12
    mid.save(output_file_path)

# Loop over the MIDI files in the directory
for midi_file in os.listdir(midi_dir):
    if midi_file.endswith(".mid"):
        midi_file_path = os.path.join(midi_dir, midi_file)
        shifted_midi_file_path = os.path.join(output_dir, os.path.splitext(midi_file)[0] + "_shifted.mid")
        output_file_path = os.path.join(output_dir, os.path.splitext(midi_file)[0] + ".wav")

        # Shift the MIDI notes up by one octave
        shift_midi_up_one_octave(midi_file_path, shifted_midi_file_path)

        # Add the shifted MIDI file to the track
        RPR.InsertMedia(shifted_midi_file_path, 0)  # 0 = add to current track

        # Wait for the pop-up and press Enter
        time.sleep(1)  # Adjust the sleep time if necessary
        reaper_window = gw.getWindowsWithTitle('REAPER')[0]
        reaper_window.activate()
        pyautogui.press('enter')

        # Set the render settings
        RPR.GetSetProjectInfo_String(0, "RENDER_FILE", output_file_path, True)
        RPR.GetSetProjectInfo(0, "RENDER_FORMAT", 0, True)  # WAV format
        RPR.GetSetProjectInfo(0, "RENDER_SRATE", 44100, True)  # Sample rate
        RPR.GetSetProjectInfo(0, "RENDER_CHANNELS", 2, True)  # Stereo
        RPR.GetSetProjectInfo(0, "RENDER_STARTPOS", 0, True)  # Start position
        RPR.GetSetProjectInfo(0, "RENDER_ENDPOS", RPR.GetProjectLength(0), True)  # End position

        # Render the project
        RPR.Main_OnCommand(41824, 0)  # Render project to disk

        # Remove the MIDI file from the track
        midi_item = RPR.GetTrackMediaItem(track, RPR.CountTrackMediaItems(track) - 1)
        RPR.DeleteTrackMediaItem(track, midi_item)

        # Notify the user
        print(f"Rendered {midi_file} to {output_file_path}")