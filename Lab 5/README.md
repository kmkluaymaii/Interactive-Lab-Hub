# Observant Systems: Overnight Sensation

**Team:**

**Members:** Afroza Aktar (aa2995), Lamiah Khan, Rawisara Chairat, Xiaoxi Xu, 

**Project name:**

# Part 1

### Part A: On-Device AI Setup

For Part A, we prepared the Raspberry Pi 5 to run artificial-intelligence models locally. We created a Python virtual environment and installed the required packages from `requirements.txt`, including Ultralytics YOLO and its dependencies. We downloaded the YOLO26 nano model and exported it to NCNN format so that it could run more efficiently on the Raspberry Pi. We tested the model on an example image and generated an annotated output image with bounding boxes around the detected objects. We also installed Ollama and downloaded the `qwen3.5:0.8b` and `qwen3:0.6b` language models. These models run directly on the Raspberry Pi without sending data to an external server. YOLO is used to observe the environment, while Qwen interprets and describes the observations. We included a screenshot of the installed models using `ollama list` and saved the generated detection images as evidence.

**Original webcam image**

<img width="640" height="480" alt="snap_original" src="https://github.com/user-attachments/assets/eb1a182e-5dcd-47ee-b10d-5b825ba54d0d" />

**YOLO annotated image**

<img width="640" height="480" alt="snap_box" src="https://github.com/user-attachments/assets/e3db542c-4b30-4d08-921b-d7184387834f" />

**OLAMA list**

<img width="826" height="464" alt="image" src="https://github.com/user-attachments/assets/ba39a87e-9cbf-408c-8510-444b1845252f" />

\*\*\***Include a screenshot of `ollama list` showing your models.**\*\*\*


### Part B: Person-Detection Experiments

We included a short video showing our person-detection experiments with YOLO running on the Raspberry Pi. The video shows the camera detecting a person, displaying a bounding box, and reporting the confidence score in the terminal. We tested different positions and movements to observe how the detector responded.

The detector did not always work perfectly. First, when we moved farther away from the camera, the person was sometimes missed because the person occupied fewer pixels in the image. Second, when we turned sideways or became partially hidden, the detector became less confident because less of the body was visible. Third, when we showed a photograph of a person, YOLO could recognize it as a person even though nobody was physically standing there. This happened because the model detects visual patterns that look like a person; it does not know whether the person is real or only printed in a photograph.

**The video is added inside lab 5 folder named 'Part_B.mp4'**

\*\*\***Include a short video or screenshots of your experiments with the person detection. Write down three situations where it did not see you, or saw a person who was not there, and what you think the cause was.**\*\*\*

### Part C: MediaPipe Hand-Pose Experiment

We included a short video of the MediaPipe hand-pose demo running on the Raspberry Pi. The video shows the webcam detecting the hand and placing colored landmark points over the fingers and face. The system tracks the hand continuously while displaying the processing speed in frames per second. As the hand moves near the face and the fingers change position, the landmark points move with it. This demonstrates that MediaPipe can identify hand locations and use their positions to recognize gestures.

**Possible Use in Our Observant System**

We could use hand-pose tracking as a touch-free control for our observant overnight system. For example, a raised hand could start monitoring before bed, a closed hand could pause the system, and a specific gesture such as a pinch or Quiet Coyote could confirm a command. Hand gestures would be useful when the user does not want to touch the Raspberry Pi or speak aloud. Face tracking could also detect whether a person is present and whether they are looking toward the device, while body-pose tracking could recognize activities such as sitting, standing, walking, or falling. These pose-based readings could be saved in the night log and summarized by Qwen in the morning.

**We uploaded the video named 'Part_C.mp4' to the Lab 5 GitHub repository**


\*\*\***Include a screenshot or short video of the hand pose demo, and write how you might use face, hand or body pose tracking in your observant system.**\*\*\*

### Part D: Qwen Results

We ran Qwen locally on the Raspberry Pi using Ollama with reasoning disabled. The `qwen3.5:0.8b` model answered the Roosevelt Island question in **11.2 seconds**, but its answer was mostly incorrect because it invented historical information. The smaller `qwen3:0.6b` model answered three ways a Raspberry Pi could observe a room in **9.8 seconds**, giving reasonable examples such as cameras, motion sensors, and environmental sensors. Finally, `qwen3.5:0.8b` analyzed `snap.jpg` in **35.8 seconds** and correctly described the person, mask, hospital gown, couch, and wallpaper. This showed that Qwen can analyze text and images locally, but it can also produce incorrect information. When Qwen is unsure, the device should say that it is uncertain instead of presenting an invented answer as fact.

<details>

#### Question 1

**Question:** Tell me a bit about the history of Roosevelt Island.  
**Model:** `qwen3.5:0.8b`  
**Time:** 11.2 seconds  

**Answer:** Roosevelt Island was originally built as a private residence for President Franklin D. Roosevelt after his inauguration. It is now a historic landmark and tourist destination known for scenic views and the Roosevelt Island Bridge.

**Evaluation:** This answer was mostly incorrect because the model invented historical information. It did not correctly mention Blackwell’s Island, Welfare Island, the 1973 renaming, or Cornell Tech.

#### Question 2

**Question:** What are three ways a Raspberry Pi can observe a room?  
**Model:** `qwen3:0.6b`  
**Time:** 9.8 seconds  

**Answer:** The Raspberry Pi can use cameras or motion sensors, monitor temperature and humidity, and collect information about user activity.

**Evaluation:** This answer was reasonable. The smaller model was faster than the `qwen3.5:0.8b` model.

#### Question 3

**Question:** What is in this photo?  
**Model:** `qwen3.5:0.8b`  
**Image:** `snap.jpg`  
**Time:** 35.8 seconds  

**Answer:** A person wearing a black face mask and a hospital gown is sitting on a brown leather couch against floral wallpaper.

**Evaluation:** This answer was mostly correct because it matched the main contents of the photograph.
</details>

\*\*\***Ask Qwen three questions to answer. Paste the questions, the answers and how long each took. Try one of them with `qwen3:0.6b` and compare.**\*\*\*

### Part E: YOLO-to-Qwen Pipeline

We connected the YOLO person detector to Qwen through a complete observation pipeline. YOLO detected people in the camera image, and the interpreter converted each detection into a text description containing the number of people, their position, and their distance from the camera. The system saved only changes in the scene to `watch_log.txt`. Qwen then used this text log to summarize what happened during the observation period. In our experiment, the system detected nobody, one person, and two people at different positions and distances. We also included the terminal screenshot, observation log, and complete program output as evidence. We uploaded the two Part E files, watch_log.txt and part_e_results.txt, inside the Part_E folder.

Files: [`watch_log.txt`](watch_log.txt), [`part_e_results.txt`](part_e_results.txt),


**observation log**

<img width="852" height="974" alt="image" src="https://github.com/user-attachments/assets/8b486f2b-0d8f-4080-8a03-0f0d5709b68c" />


# Lab 5 Part 2: Overnight Sensation

For Part 2, you will use the observant system from Part 1 to design a night-time interaction. On-device AI is slow, so let it work while you sleep. The person meets the device twice: **before bed**, when they hand the night over, and **when awake**, when the device gives something back. In between, the pipeline from Part E runs on its own.

Two flavors, pick one or mix them:

* **Sense all night.** The Pi watches, listens or measures from bedtime until morning and keeps a log.
* **Process all night.** You already have the data (a day of phone photos, a long recording) and the Pi needs hours to get through it.

Two house rules. Sample rather than stream: one look every 5 to 30 seconds is plenty, and it keeps the Pi cool. And keep everything on the Pi: tell the people you live with, point the camera at things rather than at beds, and delete the snapshots after the demo.

## Part F. 
### Read Part 2 and storyboard your night-time interaction

Storyboard a night-time interaction built on your observant system, in three panels:

1. **Before bed.** How does the person hand the night over, and how does the device acknowledge it?
2. **While asleep.** What does the device watch or work through?
3. **When awake.** What is the one thing the person learns, and in what medium?

Stuck? A kitchen that tells you who raided the fridge. A desk that reports whether you actually went to bed. A window that names the quietest hour. A plant that describes its night. Find something better.

Use storyboards and/or [Verplank diagrams](https://ccrma.stanford.edu/courses/250a-fall-2004/IDSketchbok.pdf).

\*\*\***Insert ideas, sketches, Verplank diagrams and storyboards for your night-time interaction here.**\*\*\*
For our project, we are creating a moonlight-inspired bedside device that tracks nighttime phone use to help people understand their doomscrolling habits. Before bed, the user activates the tracker with a voice command, and the device monitors for phone use throughout the night. If phone use lasts longer than five minutes, it starts a timer and logs the session until the phone is put down, repeating this process overnight without saving photos or videos. In the morning, the user presses a button to receive a summary of how many times they doomscrolled and how long each session lasted, helping them reflect on their sleep habits.
Story board: 
<img width="1163" height="580" alt="Screenshot 2026-10-28 at 5 05 17 PM" src="https://github.com/user-attachments/assets/9c58a03a-cdd8-4b00-a379-9f541eff6b6a" />

Block diagram of Moonlight Device: 
<img width="928" height="461" alt="Screenshot 2026-10-28 at 5 09 46 PM" src="https://github.com/user-attachments/assets/3a0c5289-e7fc-47a8-be21-354958a32c47" />


## Prep for Part 2

1. Look at and give feedback on the Part F storyboards.
   **Put the feedback for your ideas here.**
   Jessica Chon (GitHub: https://github.com/chonjessica23/Interactive-Lab-Hub/blob/Fall2026/Lab%205/README.md): I think your idea   is pretty useful, and the overall process seems pretty straightforward! My only question is how are you guys tracking the phone? Are you attaching sensors to it or using the models? Because my first question was wondering how would you distinguish the user from reading a book for example.

   Jianing Li: I love the interaction you designed especially the little moonlight lamp! I'm curious why did you set the 5-minute wait because if I pick up an scroll my phone for 5 minutes only, it might not be able to detect. And also, you might need to think more detailed about how your system detects the pick-up and put-down action, like maybe sample once every 10 seconds to see if the phone's still there or not?

3. [Update your Lab Hub](prep.md#get-the-latest-content) to get the latest content for Part 2.
4. Decide where the device will spend the night and who else lives there. Get their OK before the first run.
    The device will live in Rawisara and Cici's apartment in the house, near their bed side table so it can track their phone correctly.
   
6. Revise your storyboard with the feedback and with what you learned in Part E about where the pipeline breaks.

\*\*\***Post your revised storyboard here.**\*\*\*

## Part G. 
### Design the interaction before

The hand-off: the person tells the device what to watch tonight, and the device acknowledges it. Keep it to a thirty-second ritual. A button or a touch (Lab 4), a spoken sentence (Lab 3), a wave or a Quiet Coyote at the camera (Part C). The acknowledgement can be a line on the display, a tone, or an LED that dims rather than lights up. At its simplest, the hand-off just sets the question that the morning will answer.

\*\*\***Describe the interaction before.**\*\*\*

## Part H. 
### Incorporate the observant system

The Part E pipeline becomes the night shift. `overnight.py` runs your `interpret()` from `yolo_to_qwen.py` every few seconds, people only unless you pass `--all`, and writes the readings to `night_log.jsonl`; the reasoning waits for the morning. Start it inside `tmux` so it keeps running after you close your laptop, and stop it with Ctrl-C in the morning:

```
(.venv) pi@raspberrypi:~/Interactive-Lab-Hub/Lab 5 $ tmux new -s night
(.venv) pi@raspberrypi:~/Interactive-Lab-Hub/Lab 5 $ python overnight.py
```

Fake a night first: run it for thirty seconds while you walk around, stop it, and run `morning.py` from Part I. When that looks right, run a real night. If your storyboard needs a sensor rather than the camera, swap in the Lab 4 example code and log its reading the same way.

\*\*\***Screenshots or videos of the running system.**\*\*\*

## Part I. 
### Design the interaction after

The reveal. The night produced a log; the morning turns it into something a half-awake person can take in. `morning.py` is the smallest version: it asks Qwen for a three-sentence report.

```
(.venv) pi@raspberrypi:~/Interactive-Lab-Hub/Lab 5 $ python morning.py
```

Make it yours: show the report on the Mini PiTFT, read it aloud with Piper from Lab 3, plot the night as a timeline, or ask for JSON (`--json`, Part D) and move a servo. Whatever you pick, make sure it is honest about a night in which nothing happened.

## Final documentation

Document all the prototypes and iterations you have designed and worked on. The deliverables for this lab are writings, sketches, photos, and videos that show what your system:

* "Looks like": how the device sits in the room at night, and what it looks like at bedtime and in the morning.
* "Works like": the pipeline from detector to interpreter to log to reasoner, with a real night's data.
* "Acts like": how a person hands the night over and what they get back.

\*\*\***Include a short video of the whole system**\*\*\*

As always, make sure you document contributions and ideas from others (and AI) explicitly in your writeup.

You are permitted (but not required) to work in groups and share a turn in; you are expected to make equal contribution on any group work you do, and N people's group project should look like N times the work of a single person's lab. Make sure the page for the group turn in is linked to your personal Interactive Lab Hub page.

## Deliverables & Submission for Lab 5

For submission, the readme.md page for this lab should be edited to include the work you have done:
* Upload any materials that explain what you did, including your code and night log, into your Lab 5 repository, and link them in your Lab 5 readme.md.
* Labs are due on Sundays, make sure to submit your Lab 5 readme.md to Canvas.

<details>
  <summary><strong>Submission Cleanup Reminder (Click to Expand)</strong></summary>

  **Before submitting your README.md:**
  - This readme.md file has a lot of extra text for guidance.
  - Remove all instructional text and example prompts from this file.
  - You may either delete these sections or use the toggle/hide feature in VS Code to collapse them for a cleaner look.
  - Your final submission should be neat, focused on your own work, and easy to read for grading.
</details>
