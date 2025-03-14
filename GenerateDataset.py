import dawdreamer as daw
import mido
import numpy as np
import os
from scipy.io.wavfile import write
import pretty_midi
import torchcrepe
import torch
import librosa
import soundfile as sf
import SynthTab.gp_to_JAMS.process_guitarpro as gp
import SynthTab.JAMS_to_MIDI.JAMS_to_MIDI as jm
import json
from tqdm import tqdm
import copy
from concurrent.futures import ThreadPoolExecutor, as_completed
import jams
# Define the input and output directories
tabs_dir = 'C:/School/BP/Data/Tabs'
jams_dir = 'C:/School/BP/Data/Jams'
midi_dir = 'C:/School/BP/Data/Midi'
wav_dir = 'C:/School/BP/Data/Wav'
ks_config_path = 'C:/School/BP/Data/keyswitch_config.json'
tunings_json_path = 'C:/School/BP/tunings.json'

# Load the tunings from the JSON file
with open(tunings_json_path, 'r') as f:
    tunings = json.load(f)

def get_tuning(data):
    tuning = []
    for annotation in data['annotations']:
        if 'sandbox' in annotation and 'open_tuning' in annotation['sandbox']:
            tuning.append(annotation['sandbox']['open_tuning'])
    match tuning[-1]:
        case 41:
            return 1, 8
        case 40:
            return 2, 8
        case 39:
            return 3, 8
        case 38:
            return 4, 8
        case 37:
            return 5, 8
        case 36:
            return 6, 8
        case 47:
            if tuning[-2] == 54:
                return 19, 6
            else:
                return 7, 7
        case 46:
            return 8, 7
        case 45:
            return 9, 7
        case 44:
            return 10, 7
        case 43:
            return 11, 7
        case 42:
            if tuning[-2] == 49:
                return 12, 7
            else:
                return 0, 8
        case 52:
            return 14, 6
        case 51:
            return 15, 6
        case 50:
            return 16, 6
        case 49:
            return 17, 6
        case 48:
            return 18, 6
        case _:
            return 0, 8

# Function to get BPM from MIDI file
def get_bpm(midi_file):
    for track in midi_file.tracks:
        for msg in track:
            if msg.type == 'set_tempo':
                tempo = msg.tempo
                bpm = mido.tempo2bpm(tempo)
                return bpm
    return 120  # Default BPM if no set_tempo message is found

def detune_semitone(data):
    for annotation in data['annotations']:
        if 'sandbox' in annotation and 'open_tuning' in annotation['sandbox']:
            annotation['sandbox']['open_tuning'] -= 1
    return data

def uptune_semitone(data):
    for annotation in data['annotations']:
        if 'sandbox' in annotation and 'open_tuning' in annotation['sandbox']:
            annotation['sandbox']['open_tuning'] += 1
    return data

def process_jam(jam):
    with open(jam, 'r') as f:
        data = json.load(f)
    tuning, num_of_strings = get_tuning(data)
    midi_output_subdir = os.path.join(midi_dir, os.path.basename(jam).replace(".jams", ""))
    if not os.path.exists(midi_output_subdir):
        os.makedirs(midi_output_subdir)
    
    # Create a subfolder for each JAMS file
    outdir_name = os.path.splitext(os.path.basename(jam))[0]
    midi_output_dir = os.path.join(midi_output_subdir, outdir_name + "__midi")
    if not os.path.exists(midi_output_dir):
        os.makedirs(midi_output_dir)
    
    try:
        # Convert JAMS to MIDI
        tempo = jm.jams_to_midi(data, midi_output_dir, keyswitch_config)
        with open(os.path.join(midi_output_dir, "tempo.txt"), "w") as f:
            f.write(str(tempo))
    except Exception as e:
        print("Error converting file: ", jam)
        with open(os.path.join(midi_dir, "error.txt"), "a") as f:
            f.write(jam + " " + str(e) + "\n")
        print(e)
        return

    synth.set_parameter(5, tuning/19)

    # Create the corresponding directory structure in the WAV output directory
    if not os.path.exists(wav_dir):
        os.makedirs(wav_dir)

    # Process each MIDI file for synthesis
    STRINGS = num_of_strings # Number of strings
    max_length = 0
    audios = []

    for string in range(1, STRINGS + 1):
        midi_file = os.path.join(midi_output_dir, f'string_{string}.mid')
        if os.path.exists(midi_file):
            synth.load_midi(midi_file)
            midi_data = pretty_midi.PrettyMIDI(midi_file)
            duration = int(midi_data.get_end_time() + 5)
            if duration > max_length:
                max_length = duration
            graph = [(synth, [])]
            engine.load_graph(graph)
            engine.render(duration)
            audio = engine.get_audio()
            audios.append(audio)

    # Mix the audios
    audio_mix = np.zeros((2, int(max_length * sample_rate)))
    for i in range(len(audios)):
        audio_mix[:, :audios[i].shape[1]] += audios[i]
    audio_mix = audio_mix / len(audios)

    if np.max(np.abs(audio_mix)) > 0.:
        audio_mix = audio_mix * 0.99 / np.max(np.abs(audio_mix))

    # Save the mixed audio to a WAV file
    output_file_path = os.path.join(wav_dir, f'{outdir_name}.wav')
    sf.write(output_file_path, audio_mix[0].T, sample_rate, subtype='PCM_24')

    print(f"MIDI processed and saved to WAV successfully for {outdir_name}!")
def update_jam_strings(data, num_of_strings):
    strings = [annotation for annotation in data["annotations"] if annotation["namespace"] == "note_tab"]
    string_count = len(strings)
    if string_count != num_of_strings:
        difference = num_of_strings - string_count
        if difference < 0:
            # Remove annotations of the highest strings
            strings_to_remove = sorted(strings, key=lambda x: x["sandbox"]["string_index"], reverse=True)[:abs(difference)]
            for annotation in strings_to_remove:
                data["annotations"].remove(annotation)
            for annotation in strings:
                annotation["sandbox"]["string_index"] -= abs(difference)
        else:
            # Shift the indices so that the lowest string remains the lowest
            for annotation in strings:
                annotation['sandbox']['string_index'] += difference
    return data
gp.clean_jams(jams_dir)

# Search the specified directory for valid GuitarPro files
tracked_files, tracked_dirs = gp.get_valid_files(tabs_dir)

fw = open('error_files.txt', 'w')

# Loop through the tracked GuitarPro files
for gpro_file, dir in zip(tracked_files, tracked_dirs):
    print(f'Processing track \'{gpro_file}\'...')
    name = gpro_file.split('.')[0].replace('.', '-').replace(' ', '_')
    # Construct a path to GuitarPro file and JAMS output directory
    gpro_path = os.path.join(dir, gpro_file)

    # Perform the conversion
    try:
        gp.write_jams_guitarpro(gpro_path, jams_dir, name)
    except Exception as e:
        print(f'error_track: \'{gpro_file}\'...')
        print(e)
        fw.write(gpro_path + '\n')

fw.close()

with open(ks_config_path, 'r') as f:
    keyswitch_config = json.load(f)
if not os.path.exists(midi_dir):
    os.makedirs(midi_dir)

# Initialize the DawDreamer engine
sample_rate = 44100
buffer_size = 512
engine = daw.RenderEngine(sample_rate, buffer_size)

# Load the VST3 plugin
vst3_path = 'C:/Program Files/Common Files/VST3/Odin III.vst3'
synth = engine.make_plugin_processor("synth", vst3_path)
synth.load_state("C:/School/BP/odin_state.xml")

# Process each JAMS file
allJams = []
for root, dirs, files in os.walk(jams_dir):
    for file in files:
        if file.endswith(".jams"):
            allJams.append(os.path.join(root, file))

for jam in tqdm(allJams, desc="Transposing JAMS files"):
    with open(jam, 'r') as f:
        data = json.load(f)
    tuning, num_of_strings = get_tuning(data)
    tuning_name = tunings.get(str(tuning), "Unknown_Tuning")
    if tuning_name.startswith("Drop"):
        modified_jam = copy.deepcopy(data)
        modified_jam = detune_semitone(modified_jam)
        while get_tuning(modified_jam)[0] != 0:
            tuning, num_of_strings = get_tuning(modified_jam)
            tuning_name = tunings.get(str(tuning), "Unknown_Tuning")
            updated_strings_jam = copy.deepcopy(modified_jam)
            updated_strings_jam = update_jam_strings(updated_strings_jam, num_of_strings)
            with open(jam.replace(".jams", "_" + tuning_name + ".jams"), 'w') as outfile:
                json.dump(updated_strings_jam, outfile, indent=4)
            modified_jam = detune_semitone(modified_jam)
        modified_jam = copy.deepcopy(data)
        modified_jam = uptune_semitone(data)
        while get_tuning(modified_jam)[0] != 14:
            tuning, num_of_strings = get_tuning(data)
            tuning_name = tunings.get(str(tuning), "Unknown_Tuning")
            updated_strings_jam = copy.deepcopy(modified_jam)
            updated_strings_jam = update_jam_strings(updated_strings_jam, num_of_strings)
            with open(jam.replace(".jams", "_" + tuning_name + ".jams"), 'w') as outfile:
                json.dump(updated_strings_jam, outfile, indent=4)
            modified_jam = uptune_semitone(modified_jam)
    elif tuning_name.endswith("Standard"):
        print("Ahoj")
    # Update the original JAMS file
    updated_data = update_jam_strings(data, num_of_strings)
    with open(jam, 'w') as outfile:
        json.dump(updated_data, outfile, indent=4)

allJams = []
for root, dirs, files in os.walk(jams_dir):
    for file in files:
        if file.endswith(".jams"):
            allJams.append(os.path.join(root, file))
for jam in tqdm(allJams, desc="Processing JAMS files"):
    process_jam(jam)
# Create the corresponding directory structure in the MIDI output directory

