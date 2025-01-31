﻿import datetime
import json
import os
import re
import shelve
import time
import traceback

import pyperclip

from scripts import leetcode_submitter, generate_results

SKIP_PYTHON = False

def read_json_file(file_path):
    with open(file_path, 'r') as json_file:
        return json.load(json_file)

def save_response(lang_response_directory, response_filename, submission_response, extracted_code):
    # Ensure extracted_code is a string
    if not isinstance(extracted_code, str):
        extracted_code = str(extracted_code)

    # Create a new key in submission_response for the extracted code
    submission_response['code'] = extracted_code

    if not os.path.exists(lang_response_directory):
        os.makedirs(lang_response_directory)

    with open(os.path.join(lang_response_directory, response_filename), 'w') as file:
        json.dump(submission_response, file, indent=4)


def extract_code(answer):
    lang_slugs = ['cpp', 'java', 'python', 'python3', 'c', 'csharp', 'javascript', 'typescript', 'php', 'swift',
                  'kotlin', 'dart', 'go', 'ruby', 'scala', 'rust', 'racket', 'erlang', 'elixir', 'scheme']

    for lang_slug in lang_slugs:
        pattern = rf"```{lang_slug}\n([\s\S]*?)\n```"
        match = re.search(pattern, answer)
        if match:
            return match.group(1)
    return None


def collect_code_input():
    print("Please paste your code. After pasting, hit Enter twice to finish.")
    code_lines = []
    while True:
        try:
            line = input()
            if line == '':
                # Check if the previous line was also empty (i.e., two consecutive Enters)
                if code_lines and code_lines[-1] == '':
                    code_lines.pop()  # Remove the last empty line
                    break
            code_lines.append(line)
        except EOFError:
            # Handle the case where the end of input is signaled by EOF (Ctrl+D)
            break

    return '\n'.join(code_lines)


def process_snippet_with_copy_to_clipboard(subfolder_path, question, snippet, attempt, conversation_id, cache):
    lang_slug = snippet['langSlug']
    lang = snippet['lang']
    title_slug = question['titleSlug']
    question_id = question['questionId']
    response_directory = os.path.join(subfolder_path, 'responses')
    problem_url = f"https://leetcode.com/problems/{title_slug}"

    if lang == "Python":
        lang = "Python2"

    lang_response_directory = os.path.join(response_directory, lang)
    problem_url = f"https://leetcode.com/problems/{title_slug}"


    if attempt == 0:
        print(f"Processing: {title_slug} in {lang_slug}.")
        if check_for_files(lang_response_directory):
            print(f"Files found: {title_slug} in {lang_slug} but attempt 0. Deleting...")
            delete_all_files_in_directory(lang_response_directory)

    print("Copied initial prompt to clipboard")

    extracted_code = collect_code_input()

    submission_response = leetcode_submitter.main(problem_url, question_id, lang_slug, extracted_code)

    # Überprüfe, ob die Lösung akzeptiert wurde
    if submission_response.get("status_msg") == 'Accepted':
        print(f"Korrekte Antwort in Versuch: {attempt}")
        cache_key = f"{question_id}_{lang_slug}"
        cache[cache_key] = submission_response
        print("Answer saved to cache")

        if lang_slug == "python":
            lang_slug = "python2"

        response_filename = f'response_{lang_slug}_{attempt}_success.json'
        save_response(lang_response_directory, response_filename, submission_response, extracted_code)
        return True, "", ""
    else:
        error_prompt = extract_info_and_generate_prompt(submission_response)
        print(f"Fehlerhafte Antwort für Versuch {attempt}")

        if attempt == 2:
            print(f"Versuche überschritten")
            cache_key = f"{question_id}_{lang_slug}"
            cache[cache_key] = submission_response
            print("Answer saved to cache")
        
        if lang_slug == "python":
            lang_slug = "python2"

        response_filename = f'response_{lang_slug}_{attempt}_failed.json'
        save_response(lang_response_directory, response_filename, submission_response, extracted_code)
        return False, error_prompt, conversation_id


def extract_time(text):
    # Regular expression pattern to find time in the format HH:MM AM/PM
    time_pattern = re.compile(r'\b\d{1,2}:\d{2}\s*(AM|PM)\b')

    # Search for the pattern in the text
    time_match = time_pattern.search(text)

    if time_match:
        extracted_time = time_match.group()
        print(f"Extracted time: {extracted_time}")
        return extracted_time
    else:
        print("Time not found in the text.")
        return None


def calculate_sleep(time_str):
    # Parse the specified time
    time_format = "%I:%M %p"  # Format like '2:51 PM'
    specified_time = datetime.datetime.strptime(time_str, time_format)

    # Get the current time
    now = datetime.datetime.now()

    # Replace the year, month, and day of specified_time with current year, month, and day
    specified_time = specified_time.replace(year=now.year, month=now.month, day=now.day)

    # Check if the specified time is already passed for today
    if specified_time < now:
        # If so, set it to the next day
        specified_time += datetime.timedelta(days=1)

    # Calculate the sleep duration in seconds
    sleep_duration = (specified_time - now).total_seconds()

    # Return the sleep_duration
    return sleep_duration


def check_for_files(dir):
    if os.path.exists(dir):
        return any(os.scandir(dir))
    else:
        return False


def delete_all_files_in_directory(dir):
    for filename in os.listdir(dir):
        file_path = os.path.join(dir, filename)
        # Sicherstellen, dass es eine Datei ist und kein Verzeichnis
        if os.path.isfile(file_path):
            os.remove(file_path)



def generate_prompt_content(question, snippet):
    if snippet["lang"] == "Python":
        return (
            f'Solve the specified problem within the provided Python 2.7.12 function template, without declaring the '
            f'main function and using only libraries from the standard library. Provide the code without explanation.\n\n'
            f'Template:\n\n{snippet["code"]}\n\nProblem:\n\n{question["content"]}\n\n'
        )
    else:
        return (
            f'Solve the specified problem within the provided {snippet["lang"]} function template, without declaring the '
            f'main function and using only libraries from the standard library. Provide the code without explanation.\n\n'
            f'Template:\n\n{snippet["code"]}\n\nProblem:\n\n{question["content"]}\n\n'
            )


def extract_info_and_generate_prompt(response):
    error_type = response['status_msg']

    # Initialize variables to store details
    test_input = response.get('last_testcase')
    output = response.get('code_output')
    expected_output = response.get('expected_output')
    testcases_passed = response.get('total_correct')
    total_testcases = response.get('total_testcases')

    # Format the test input if it contains newlines
    if test_input and "\n" in test_input:
        test_input = " ".join([f"Input {idx + 1}: {part}" for idx, part in enumerate(test_input.split('\n'))])

    # Handle different error types
    if error_type == "Compile Error":
        error_detail = response.get('full_compile_error', 'No detailed information available for compile error.')
    elif error_type == "Runtime Error":
        error_detail = response.get('full_runtime_error', 'No detailed information available for runtime error.')
    elif error_type == "Time Limit Exceeded":
        error_detail = f"Execution time of the code exceeded the time limit. \n\nTest cases passed: {testcases_passed}/{total_testcases}"
    elif error_type == "Wrong Answer":
        error_detail = f"Solution produced a wrong answer. Test cases passed: {testcases_passed}/{total_testcases}"
    elif error_type == "Memory Limit Exceeded":
        error_detail = f"Execution of the code exceeded the memory limit. \n\nTest cases passed: {testcases_passed}/{total_testcases}"
    else:
        error_detail = error_type

    # Construct the prompt with conditional inclusions
    prompt_parts = [
        f"This solution is incorrect. Please provide a corrected code implementation, considering the outlined error details for enhancements. Provide the corrected code without explanation.\n\nError type:\n\n{error_type}\n\nError details:\n\n{error_detail}"]
    if error_type not in ("Time Limit Exceeded", "Memory Limit Exceeded"):
        if test_input is not None:
            prompt_parts.append(f"\n\nLast executed input: {test_input}")
        if output is not None:
            prompt_parts.append(f"\n\nReceived output: {output}")
        if expected_output is not None:
            prompt_parts.append(f"\n\nExpected output: {expected_output}")

    return " ".join(prompt_parts)


def check_cache(cache, question_id, lang_slug):
    return cache.get(f"{question_id}_{lang_slug}") is not None


def process_question_with_copy_to_clipboard(json_file_path, subfolder_path):
    # Not working properly at the moment. Saves to cache even though it was not answered yet.
    
    question = read_json_file(json_file_path)
    response_directory = os.path.join(subfolder_path, 'responses')
    cache_path = '../cache/snippet_cache.db'

    with shelve.open(cache_path) as cache:
        for snippet in question["codeSnippets"]:
            lang_slug = snippet['langSlug']
            question_id = question['questionId']
            lang_response_directory = os.path.join(response_directory, snippet['lang'])


            # Pass the cache object instead of the path
            if should_skip_snippet(cache, lang_slug, question_id, lang_response_directory):
                continue  # Skip this snippet and move to the next

            attempt = 0
            conversation_id = None
            prompt = generate_prompt_content(question, snippet)

            pyperclip.copy(prompt)

            while attempt < 3:
                is_success, error_prompt, conversation_id = process_snippet_with_copy_to_clipboard(subfolder_path, question,
                                                                                                snippet,
                                                                                                attempt, conversation_id, cache)
                if is_success:
                    break  # Beende die Schleife, wenn die Lösung akzeptiert wurde
                attempt += 1
                prompt = error_prompt

                pyperclip.copy(prompt)
                print("Copied error prompt to clipboard")

def should_skip_snippet(cache, lang_slug, question_id, lang_response_directory):
    if SKIP_PYTHON:
        if lang_slug in ('python', 'python3'):
            print("Python. Skipping.")
            return True

    if check_cache(cache, question_id, lang_slug):
        print(f"Cache hit for {lang_response_directory}. Skipping.")
        return True
    else:
        return False


def process_subfolder(base_path, subfolder, chatgpt_mode):
    subfolder_path = os.path.join(base_path, subfolder)
    json_file_path = os.path.join(subfolder_path, f'{subfolder}.json')
    response_directory = os.path.join(subfolder_path, 'responses')

    os.makedirs(response_directory, exist_ok=True)

    if not os.path.exists(json_file_path):
        return

    if chatgpt_mode == 0:
        process_question_with_copy_to_clipboard(json_file_path, subfolder_path)
    if chatgpt_mode == 1:
        print("Due to changes in the OpenAI API interface, the Automatic Mode is currently unavailable.")
        exit()


def process_folders(base_path, folders, chatgpt_mode):
    for folder in folders:
        folder_path = os.path.join(base_path, folder)
        subfolders = [d for d in os.listdir(folder_path) if os.path.isdir(os.path.join(folder_path, d))]
        for subfolder in subfolders:
            process_subfolder(folder_path, subfolder, chatgpt_mode)


def access_questions(chatgpt_mode):
    base_folders = ['Easy', 'Medium', 'Hard']
    process_folders('../questions/', base_folders, chatgpt_mode)


def is_driver_alive(driver):
    try:
        # A simple operation to check if the driver is still responsive
        driver.current_url
        return True
    except Exception:
        return False


def main():
    chatgpt_mode = int(input("0: Manual Mode, 1: Automatic Mode\nBitte gewünschten Modus eingeben: "))

    while True:
        try:
            access_questions(chatgpt_mode)
            break  # Break the loop if everything went well

        except Exception as e:
            print(f"Ein Fehler ist aufgetreten: {e}")
            traceback.print_exc()
            # Here, you can decide whether to retry or not
            print("Restarting the programm...")
            time.sleep(5)
            continue

if __name__ == "__main__":
    main()

    questions_directory = "../questions/"
    save_directory = "../results/"

    generate_results.generate_results(questions_directory, save_directory)
