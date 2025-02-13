import google.generativeai as genai
import json
import os
from datetime import datetime

from termcolor import colored

import typing_extensions as typing

class AiResponseJDScore(typing.TypedDict):
    score: float
    reasoning: str
    questions: list[str]    
    need_cv: bool

class AiResponseCVScore(typing.TypedDict):
    score: float
    reasoning: str
    questions: list[str]    


# read prompt scoring-prompt.txt
with open('jd-scoring-prompt.txt', 'r') as file:
    jd_scoring_prompt = file.read()

with open('cv-scoring-prompt.txt', 'r') as file:
    cv_scorint_prompt = file.read()


with open('cv-scoring-prompt.txt', 'r') as file:
    cv_scoring_prompt = file.read()

with open('cv_markdown.txt', 'r') as file:
    cv_markdown = file.read()

with open('cover-letter-prompt.txt', 'r') as file:
    letter_prompt = file.read()


with open('tailor-cv-prompt.txt', 'r') as file:
    cv_tailor_prompt = file.read()


apikey = ''
with open('apikey') as f: apikey = f.read()
apikey= apikey.rstrip('\r\n')
#print(f"apikey is \"{apikey}\"")
genai.configure(api_key=apikey)
model = genai.GenerativeModel("gemini-2.0-flash-exp")
#print(response.text)

minute_variable = datetime.now().minute
counter = 0
max_rpm = 12

import time

def rate_limited_generate_content(model, prompt, generation_config = None ):
    global counter, minute_variable
    current_minute = datetime.now().minute

    if current_minute != minute_variable:
        cointer = 0
        minute_variable = current_minute

    if counter >= max_rpm:
        time_to_wait = 60 - datetime.now().second
        print(f"Rate limit reached. Waiting for {time_to_wait} seconds.")
        time.sleep(time_to_wait)
        counter = 0
        minute_variable = datetime.now().minute

    response = model.generate_content(prompt, generation_config=generation_config)
    counter += 1
    return response


# Directory containing the job descriptions
jds_dir = 'jds'
jd_scores_dir = 'jd_scores'
cv_scores_dir = 'cv_scores'
tailored_cv_dir = 'tailored_cv'
tailored_letter_dir = 'tailored_letter'

# need to average response otherwise they are QUITE random, minimum 3, better 5 or more, but timeouts too much for bigger numbers
retries = 5

# Iterate over each file in the jds directory
for filename in os.listdir(jds_dir):
    if filename.endswith('.txt'):
        
        # Read the job description
        with open(os.path.join(jds_dir, filename), 'r') as jd_file:
            job_description = jd_file.read()
        
        # Create the prompt by appending the job description to the end of the initial prompt
        full_prompt = f"{jd_scoring_prompt}\n\n{job_description}"

        print(f"Testing {filename}\n")

        once = True

        for attempt in range(retries):
            score_file_path = os.path.join(jd_scores_dir, f"{attempt}_{filename}")

            if os.path.exists(score_file_path):
                print(f"Score file {score_file_path} already exists. Skipping generation.")
                continue

            # Send the prompt to the model
            response = rate_limited_generate_content(model, full_prompt,  generation_config=genai.GenerationConfig(
                response_mime_type="application/json", response_schema=AiResponseJDScore
            ))
                        
            # regenerate response if CV requested
            if ('need_cv' in response and not ('score' in response)):
                response = rate_limited_generate_content(model, f"{full_prompt} ---\n CV: {cv_markdown}" ,  generation_config=genai.GenerationConfig(
                    response_mime_type="application/json", response_schema=AiResponseJDScore
                ),) 

            # put response into jd_scores_dir dir with same filename
            # Save the response text to a file in the jd_scores_dir directory with the same filename
            

            with open(score_file_path, 'w') as score_file:
                score_file.write(response.text)

                # Parse the response text as JSON
                response_data = json.loads(response.text)

                color = 'white'

                if not ('score' in response_data):
                     print(f"Response_data - {response_data}, score empty ? {filename}\n")
                     # why sometimes scores are not computed ?
                     response_data['score'] = 0

                # Check if the score is greater than 5 (can jump +\- 1 depending on random)
                if response_data['score'] >= 6:
                    # Highlight the response in bright green
                    color = 'green'
                    print(colored(f"Score for JD {response_data['score']} for {filename}\n", color, attrs=['bold']))
                    
                else:
                    color = 'red'
                    print(colored(f"Score for JD {response_data['score']} for {filename}\n", color))

                #print reasoanign for "middle" casue it might be wrong 
                if (response_data['score'] >= 3 and response_data['score'] <= 6):
                    print(colored(f"Reasoning for JD score: {response_data['reasoning']}\n", 'white'))

                if response_data['score'] <= 4:
                    color = 'red'

                if 'questions' in response_data:
                    print(colored(f"Questions: {response_data['questions']}\n", color))

                if 'need_cv' in response_data or response_data['score'] >= 5:

                    #if count of questions is  less than equal 2 bother to match cv vs job 
                    response_cv = rate_limited_generate_content(model, f"{cv_scoring_prompt} JD: \n\n{job_description} CV: \n\n{cv_markdown}", generation_config=genai.GenerationConfig(
                        response_mime_type="application/json", response_schema=AiResponseCVScore
                    ),)

                    #print(response_cv)

                    with open(os.path.join(cv_scores_dir, f"{attempt}_{filename}"), 'w') as score_file:
                        score_file.write(response_cv.text)

                    response_data_cv = json.loads(response_cv.text)

                    color = 'white'

                    if response_data_cv['score'] >= 8:
                        color = 'green'

                    if response_data_cv['score'] < 6:
                        color = 'red'
                    
                    if response_data_cv['score'] >= 6:
                        # only try letter generative once
                        tailored_cv_file_path = os.path.join(tailored_cv_dir, f"{filename}");
                        if once or not (os.path.exists(score_file_path)):
                            once = False                            
                            # generative CV tailored to JD
                            tailored_cv_reponse = rate_limited_generate_content(model, f"{cv_tailor_prompt} JD: \n\n{job_description} CV: \n\n{cv_markdown}")

                            with open(tailored_cv_file_path, 'w') as tailored_cv_file:
                                tailored_cv_file.write(tailored_cv_reponse.text)
                            
                            # generate cover letter
                            response_letter = rate_limited_generate_content(model, f"{letter_prompt} JD: \n\n{job_description} CV: \n\n{cv_markdown}")

                            with open(os.path.join(tailored_letter_dir, f"{filename}"), 'w') as tailored_letter_file:
                                tailored_letter_file.write(response_letter.text)

                            print(colored(f"Generated CV/LETTER for {filename}\n", 'green', attrs=['bold'] ))
                        else:
                            print(colored(f"Skipped letter-gen\n", 'white'))
                    else:
                        color = 'red'
                        
                    print(colored(f"Score for CV {response_data_cv['score']}\n", color, attrs=['bold']))

                    if 'questions' in response_data_cv:
                        print(colored(f"Questions - {response_data_cv['questions']}\n", color, attrs=['bold']))
                    print(colored(f"Reasoning for CV score {response_data_cv['reasoning']}\n", color))
                else:
                    print("Skipped because of bad jd scoring!")



scores = []
# Read scores from jd_scores directory and cv_scores directory
jd_scores = []
cv_scores = []

# Read scores from jd_scores directory and cv_scores directory, accounting for "attempt" prefix in filenames
jd_score_dict = {}
cv_score_dict = {}

for filename in os.listdir(jd_scores_dir):
    if filename.endswith('.txt'):
        with open(os.path.join(jd_scores_dir, filename), 'r') as score_file:
            #print(score_file), # in case of ctrl-c and broken file uncomment for debug
            score_data = json.load(score_file)
            # Remove "attempt" prefix from filename
            actual_filename = filename.split('_', 1)[1]
            if actual_filename not in jd_score_dict:
                jd_score_dict[actual_filename] = []
            if 'score' in score_data:
                jd_score_dict[actual_filename].append(score_data['score'])

for filename in os.listdir(cv_scores_dir):
    if filename.endswith('.txt'):
        with open(os.path.join(cv_scores_dir, filename), 'r') as score_file:
            score_data = json.load(score_file)
            # Remove "attempt" prefix from filename
            actual_filename = filename.split('_', 1)[1]
            if actual_filename not in cv_score_dict:
                cv_score_dict[actual_filename] = []
            if 'score' in score_data:
                cv_score_dict[actual_filename].append(score_data['score'])

# Calculate average scores
jd_scores = []
for filename, scores in jd_score_dict.items():
    average_score = sum(scores) / len(scores)
    dispersion = max(scores) - min(scores)
    root_dispersion = dispersion ** 0.5
    jd_scores.append((filename, average_score, root_dispersion))
    #print(f"JD Filename: {filename}, Average Score: {average_score}, Root Dispersion: {root_dispersion}")

cv_scores = []
for filename, scores in cv_score_dict.items():
    average_score = sum(scores) / len(scores)
    dispersion = max(scores) - min(scores)
    root_dispersion = dispersion ** 0.5
    cv_scores.append((filename, average_score, root_dispersion))
    #print(f"JD Filename: {filename}, Average Score: {average_score}, Dispersion: {dispersion}")


# Combine JD scores and CV scores
combined_scores = []
for jd_score in jd_scores:
    for cv_score in cv_scores:
        if jd_score[0] == cv_score[0]:
            combined_scores.append((jd_score[0], jd_score[1], cv_score[1], jd_score[2], cv_score[2]))

# Sort filenames by JD score first, then by CV score
sorted_combined_scores_by_jd = sorted(combined_scores, key=lambda x: (x[1], x[2]), reverse=True)

sorted_combined_scores_by_cv = sorted(combined_scores, key=lambda x: (x[2], x[1]), reverse=True)

print(colored(f"Recommended applying order by JD:\n", 'green'))

# Display filenames sorted by JD score and then by CV score
for filename, jd_score, cv_score, jd_dispersion, cv_dispersion in sorted_combined_scores_by_jd:
    print(f"Filename: {filename}, JD Score: {jd_score}+\-{jd_dispersion}, CV Score: {cv_score}+\-{cv_dispersion}")



print(colored(f"Recommended applying order by CV:\n", 'green'))

# Display filenames sorted by JD score and then by CV score
for filename, jd_score, cv_score, jd_dispersion, cv_dispersion in sorted_combined_scores_by_cv:
    print(f"Filename: {filename}, JD Score: {jd_score}+\-{jd_dispersion}, CV Score: {cv_score}+\-{cv_dispersion}")

