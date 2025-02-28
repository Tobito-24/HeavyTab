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

# Define the input and output directories
tabs_dir = 'C:/School/BP/Data/Tabs'
jams_dir = 'C:/School/BP/Data/Jams'
midi_dir = 'C:/School/BP/Data/Midi'
wav_dir = 'C:/School/BP/Data/Wav'
ks_config_path = 'C:/School/BP/Data/keyswitch_config.json'

def get_tuning(JAMS_file):
    with open(JAMS_file, 'r') as f:
        data = json.load(f)
    tuning = []
    for annotation in data['annotations']:
        if 'sandbox' in annotation and 'open_tuning' in annotation['sandbox']:
            tuning.append(annotation['sandbox']['open_tuning'])
    print(tuning)
    match tuning[-1]:
        case '41':
            return 1, 8
        case '40':
            return 2, 8
        case '39':
            return 3, 8
        case '38':
            return 4, 8
        case '37':
            return 5, 8
        case '36':
            return 6, 8
        case '47':
            if tuning[-2] == '54':
                return 19,6
            else:
                return 7, 7
        case '46':
            return 8, 7
        case '45':
            return 9, 7
        case '44':
            return 10, 7
        case '43':
            return 11, 7
        case '42':
            if tuning[-2] == '49':
                return 12, 7
            else:
                return 0, 8
        case '52':
            return 14,6
        case '51':
            return 15, 6
        case '50':
            return 16, 6
        case '49':
            return 17, 6
        case '48':
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

gp.clean_jams(jams_dir)

# Search the specified directory for valid GuitarPro files
tracked_files, tracked_dirs = gp.get_valid_files(tabs_dir)

fw = open('error_files.txt', 'w')

# Loop through the tracked GuitarPro files
for gpro_file, dir in zip(tracked_files, tracked_dirs):
    print(f'Processing track \'{gpro_file}\'...')

    # Construct a path to GuitarPro file and JAMS output directory
    gpro_path = os.path.join(dir, gpro_file)
    jam_dir = os.path.join(jams_dir, gpro_file.split('.')[0].replace('.', '-').replace(' ', '_'))

    # Perform the conversion
    try:
        gp.write_jams_guitarpro(gpro_path, jam_dir)
    except:
        print(f'error_track: \'{gpro_file}\'...')
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

# Process each JAMS file
allJams = []
for root, dirs, files in os.walk(jams_dir):
    for file in files:
        if file.endswith(".jams"):
            allJams.append(os.path.join(root, file))

for jam in tqdm(allJams, desc="Processing JAMS files"):
    tuning, num_of_strings = get_tuning(jam)
    # Create the corresponding directory structure in the MIDI output directory
    relative_path = os.path.relpath(jam, jams_dir)
    midi_output_subdir = os.path.join(midi_dir, os.path.dirname(relative_path))
    if not os.path.exists(midi_output_subdir):
        os.makedirs(midi_output_subdir)
    
    # Create a subfolder for each JAMS file
    outdir_name = os.path.splitext(os.path.basename(jam))[0] + "__midi"
    midi_output_dir = os.path.join(midi_output_subdir, outdir_name)
    if not os.path.exists(midi_output_dir):
        os.makedirs(midi_output_dir)
    
    try:
        # Convert JAMS to MIDI
        tempo, stringCount = jm.jams_to_midi(jam, midi_output_dir, keyswitch_config, num_of_strings)
        with open(os.path.join(midi_output_dir, "tempo.txt"), "w") as f:
            f.write(str(tempo))
    except Exception as e:
        print("Error converting file: ", jam)
        with open(os.path.join(midi_dir, "error.txt"), "a") as f:
            f.write(jam + " " + str(e) + "\n")
        print(e)
        continue

    synth.set_parameter(5, tuning/19)

    # Create the corresponding directory structure in the WAV output directory
    wav_output_subdir = os.path.join(wav_dir, os.path.dirname(relative_path))
    if not os.path.exists(wav_output_subdir):
        os.makedirs(wav_output_subdir)

    # Process each MIDI file for synthesis
    STRINGS = stringCount # Number of strings
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
    output_file_path = os.path.join(wav_output_subdir, f'{outdir_name}.wav')
    sf.write(output_file_path, audio_mix[0].T, sample_rate, subtype='PCM_24')

    print(f"MIDI processed and saved to WAV successfully for {outdir_name}!")