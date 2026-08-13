Music Library Structure for Hybrid Zero-Cost Video Pipeline

Since we are building a zero-cost pipeline, downloading royalty-free music 
dynamically using APIs often costs money or has strict rate limits. 

Instead, download 5-10 MP3/WAV tracks from these free sources:
- Pixabay Music: https://pixabay.com/music/
- YouTube Audio Library: https://studio.youtube.com/channel/UC/music
- ccMixter: http://ccmixter.org/

Place the downloaded files into one of the following folders based on the energy of the track:

1. calm/
   - Slow, ambient, emotional, or quiet tracks.
   - Used for the "Problem" and "Agitate" acts of the video to build tension.

2. upbeat/
   - Happy, positive, bouncy, or energetic tracks.
   - Used for the "Solution" and "Proof" acts.

3. urgent/
   - Fast, driving, intense, or ticking-clock style tracks.
   - Used for the "CTA" (Call To Action) act.

The system will randomly pick a track from the dominant energy level of the video.
It will automatically loop the track if it's too short, fade it out at the end, 
and mix it underneath the voiceover (-18dB).
