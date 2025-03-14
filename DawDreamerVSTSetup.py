import dawdreamer as daw

# Initialize the DawDreamer engine
sample_rate = 44100
buffer_size = 512
engine = daw.RenderEngine(sample_rate, buffer_size)

# Load the VST3 plugin
vst3_path = 'C:/Program Files/Common Files/VST3/Odin III.vst3'
synth = engine.make_plugin_processor("synth", vst3_path)
synth.load_state("C:/School/BP/odin_state.xml")
synth.open_editor()
print("ahoj")
synth.save_state("C:/School/BP/odin_state.xml")