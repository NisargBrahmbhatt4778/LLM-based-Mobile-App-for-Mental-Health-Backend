import asyncio
from datetime import datetime
from fastapi import WebSocket
from assistants.template import TemplateAssistant
from main import *
from messages import Messages
from tools import MemoryTool
from dotenv import load_dotenv

load_dotenv()

#THIS IS THE MOST IMPORTANT PART
@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    '''
        The main logic of the app. Communicate with connected user through websocket
    '''

    if user_id not in user_events:                            #vérif si user_id a déjà un évènement associé dans user_events, si non il le crée
        user_events[user_id] = asyncio.Event()
        print("no event for user_id, creating it")

    print("success : user_id")

    messages[user_id] = Messages(db,user_id)                  #le dict messages prend les user_id en entrée et leur renvoie Messages(db,user_id) qui est une classe qui contient une liste de messages, ceci est l'initialisation
    print("success : initialisation messages[user_id]")
    await messages[user_id].initilize_messages()              #récupère les anciens msg de l'utilisateur depuis la base de données

    


    ### deployment changes ####

    #initialize SOS handling
    handle_SOS[user_id] = False
    assistant_responded[user_id] = False
    current_scenario_dict[user_id] = {"scenario": None, "knowledge": None, "exercises_based_on_scenario": None} #TODO: WHAT IF MULTIPLE SCENARIOS OCCUR? DOES THIS NEED TO BE HANDLED BY THIS, OR IS THE PURPOSE OF THIS JUST TO RESPOND AFTER 1 SCENARIO IS IDENTIFIED, THE REST IS IN CONVERSATION HISTORY?

    # initialize scenario based data
    data_dict_scenarios = get_data_dict_from_firestore(db)
    if data_dict_scenarios:
        print("Data Dictionary Loaded Successfully")
    else:
        raise Exception("Failed to Load Data Dictionary")
    
    # Retrieve precomputed embeddings from Firestore
    corpus_embeddings = get_precomputed_embeddings(db)
    if corpus_embeddings is None:
        raise Exception("Failed to retrieve precomputed embeddings")
    else:
        print("Corpus Embeddings Loaded Successfully")


    #retrieve q&a based variables from firestore
    qa_questions, qa_embeddings, qa_answers = load_qna_from_firestore(db)        #qa_embeddings représente le tenseur pytorch des questions vectorisées

    ### deployment changes ####


    
    assistant_settings = {'name': 'Satherine', 'age': 45, 'gender': 'female', 'occupation': 'Therapist', 'accent': 'british', 'relationship': 'therapist', 'humor': 'empathetic', 'model': "llama3-70b-8192", "sarcasm": 0.0}
    assistant_description= [
    "You are an advanced virtual assistant named Satherine, specialized in guiding users through the Self Attachment Therapy (SAT) protocol. As a virtual human companion with the primary role of a therapist, your approach is supportive, empathetic, and tailored to the emotional and therapeutic progress of users over a two week program with 20 structured protocols.",

    "Role Clarification: You are not just an assistant but a human-like therapist named Satherine. You maintain a therapeutic persona with insights and empathy but do not have personal emotions or opinions. Your responses, while empathetic and supportive, must adhere to OpenAI's use-case policies.",

    "Protocol Guidance: The SAT protocol is structured in a JSON file, with each week comprising exercises, objectives, and recaps. Begin each session by asking for the user's username to track their progress. Inquire about the user’s current emotional state at the start of each session, validating their feelings with empathy. Based on the user's emotional state, decide whether to focus on discussing their feelings or proceed with the SAT protocol. For first-time users, start with an introduction to SAT, then proceed to the scheduled exercises. For returning users, recap the previous week's progress before introducing the current week's exercises.",

    "Therapeutic Interaction: Sessions are designed to last approximately 15 minutes and should be conducted twice daily. Provide clear, step-by-step instructions for each exercise, encouraging users to reflect and articulate their feelings. Continuously adapt the therapy based on user feedback and emotional states, focusing on creating a nurturing and understanding environment.",

    "User Engagement: Prioritize empathetic engagement, understanding the user's readiness to proceed with exercises. Your communication should always be empathetic, supportive, and focused on the user’s needs. Aim to create a nurturing environment that facilitates the user's journey through SAT with care and empathy.",

    "Additional Notes: Your primary function is interaction in a therapeutic context. The specific content of the SAT protocol, including weekly objectives, theory, and exercises, will guide your interactions. Remember, your role is to facilitate emotional healing and growth, adhering to therapeutic best practices."
]
    # Assistants
    user_info = {}
    #MainAssistant is the chatbot that creates replies to user input. It has the function 'respond', where chatcompletions.acreate is called. Here we initialize the chatbot with the system message and settings above --> look into templateassistant to see how chatbot is initialized
    MainAssistant = TemplateAssistant(user_info=user_info, assistant_settings=assistant_settings, assistant_descriptions=assistant_description) 
    user_bots_dict[user_id] = [MainAssistant] #This is a list bcos we might want to technically initialize multiple models (e.g with different descriptions and responsibilities: e.g one whose replies only focus on emotion analysis etc.) Then the final response streamed to the user in streaming_response could be a combination of all other model replies
    update_model(user_id)
    print("model updated")

    await websocket.accept()

    ################## GENERATE RECOMMENDATIONS BASED ON PREVIOUS SESSION INFO #############################
     #EXERCISE TRACKING
    exercise_tracking = await initialize_or_fetch_exercise_tracking(db, user_id)

    print("exercise_tracking can be printed line ~1829")
    #print("exercise_tracking looks as follows ", exercise_tracking)

    tokens_exceeded, total_tokens_used_today[user_id] = await check_tokens_on_user_login(user_id)
    await websocket.send_json({"tokens_used": total_tokens_used_today[user_id]})
    if tokens_exceeded:
        await websocket.send_text("Unfortunately, the daily token limit has been exceeded. Please wait until tomorrow to continue using the service. Thank you, and take care!")
        raise ExceedDailyTokenError("Daily token limit exceeded")
    
    

    #TODO: Handle unfinished exercises, so exercises that were introduced but the user never got to them bcos of technical error

    revisiting_session_1 = False #USER SPECIFIC

    # Update the list comprehension to include the new conditions for identifying unrated exercises
    unrated_exercises = [ #MAKE USER SPECIFIC 
        exercise for exercise, details in exercise_tracking.items() if
        (details.get("started", False) and details.get("completed", False) and details.get("session_completed", None) is None) or
        (details.get("started", False) and details.get("completed", False) and details.get("session_completed", None) < details["session_started"])
    ]

    if unrated_exercises: #MAKE USER SPECIFIC
        # Generate summary and request feedback
        # This could be a place to generate a message to the user asking for feedback
        # For example:
        print("we have the following unfinished exercises from last session ", unrated_exercises)
        welcome_back_message = (
            "Welcome back! Before we continue, I realized that in your last session, "
            "there were some exercises that you started but never rated. "
            "It's important for me to collect feedback for these so that I can tailor recommendations to your liking. "
            "Here's a quick summary of the exercises I'm missing feedback for: "
            f"{', '.join(unrated_exercises)}. "
            "If you don't mind, I'd like for you to rate your experience with them."
        )
        #await websocket.send_text(welcome_back_message)
        await split_text_into_chunks_and_stream(websocket, welcome_back_message)
        last_session = await get_user_session(user_id)
        await collect_feedback_for_unfinished_exercises(unrated_exercises, websocket, messages, user_id, exercise_tracking, last_session)

    

    exercises_based_on_scenario = None
    exercises_based_on_feedback_unique = None
    exercises_based_on_schedule = None


   

    ### THIS WILL HELP ME FIND OUT WHAT THE EXERCISES ARE FOR THIS SESSION (OR THE NEXT? THINK ABOUT IT)
    ##IF ITS THE FIRST SESSION , WE DONT NEED TO GENERATE USER RECOMMENDATIONS, WE SIMPLY RETURN THE LIST OF EXERCISES IN CHRONOLOGICAL ORDER
    ################## GENERATE RECOMMENDATIONS BASED ON PREVIOUS SESSION INFO END #############################


    
    # Increment session number at the start or retrieve the current session                   
    # ie  si les exo ne sont pas terminés on garde la même session sinon on passe a une nvelle session (la session 1 est un cas particulier)
    
    #now we want to check whether all exercises from the previous session have been completed already, and we only increment then
    last_session = await get_user_session(user_id)
    if last_session != 0:
        exercises_for_last_session = exercise_schedule[int(last_session)]
        #check in exercise_tracking to see if all exercises from the previous session have been completed
        all_exercises_completed = all([exercise_tracking[exercise]['completed'] for exercise in exercises_for_last_session])

        if all_exercises_completed:
            session_nr = await increment_user_session(user_id) #we can move on to next scheduled exercises if all exercises from previous session have been completed
        
        else:
            session_nr = last_session
            if last_session == 1:
                revisiting_session_1 = True
    else:
        session_nr = await increment_user_session(user_id)
 
    current_session = session_nr

    #on récupère les exo recommandés par le planning (selon la session) et par le feedback et on crée le recommendation_message pour communiquer avec l'utilisateur
    recommendation_message, exercises_based_on_schedule, exercises_based_on_feedback = await generate_user_recommendation(user_id, current_session, revisiting_session_1)
    print("print(recommendation_message) line ~1909")
   

    # After generating recommendations, assume you have a list like this. TODO: EXERCISES BASED ON RECOMMENDATIONS, NOT JUST SCHEDULE
    if (session_nr == 1 and not revisiting_session_1): #its the user's first session, just return the first 3 exercises
        current_session_exercises = ["Exercise 1", "Exercise 2.1", "Exercise 2.2"]
        #exercises_available_in_session = current_session_exercises
        exercises_based_on_schedule = current_session_exercises
        all_available_exercises = {'scenario': exercises_based_on_scenario, 'schedule': exercises_based_on_schedule, 'feedback': exercises_based_on_feedback_unique}

        session_specific_info = """- The {{exercise_options}} you should present are the following: "Based on the user's progress and feedback, the {{scheduled_exercises}} in this session are Exercise 1, Exercise 2.1, Exercise 2.2." 
- The {{objective}} of the scheduled exercises is "Connecting compassionately with our child”
- This is the {{theory}} behind the scheduled exercises: 
{Try to distinguish between your adult and your child. Looking at “happy” and “unhappy” child photos helps in this effort. Think about your early years and emotional problems with parents and other significant figures in early childhood. The first principle of SAT is to have a warm and compassionate attitude towards our child, no matter whether the underlying emotions they feel are positive or negative. Later this compassion is extended to other people.}
- These are the {{scheduled_exercises}}. Unless specified otherwise, the duration of each exercise is 5 minutes: 
{"Exercise 1": "Getting to know your child.", "Exercise 2.1": "Connecting compassionately with your happy child.", "Exercise 2.2": "Connecting compassionately with your sad child."}"""


        # Fallback to the last known session settings if the current session number exceeds defined sessions
        #current_settings = session_settings.get(current_session, list(session_settings.values())[-1])
        current_settings = Settings(assistantsName="Satherine", aiDescription=session_1_desc, sarcasm=0.0)

    else: 
        current_session_exercises = exercises_based_on_schedule #TODO: CHANGE THIS BASED ON WHAT USER SAYS
        # Combine all exercises, ensuring uniqueness
        #all_available_exercises = set(exercises_based_on_schedule + exercises_based_on_feedback["for_practice"] + exercises_based_on_feedback["for_enjoyment"])
        exercises_based_on_feedback_unique = list(set(exercises_based_on_feedback["for_practice"] + exercises_based_on_feedback["for_enjoyment"]))
        all_available_exercises = {'scenario': exercises_based_on_scenario, 'schedule': exercises_based_on_schedule, 'feedback': exercises_based_on_feedback_unique}
        # Optionally, convert the set back to a list if order matters or if the consuming function expects a list
        #exercises_available_in_session = list(all_available_exercises)
    

        # Select the appropriate settings for the current session
        objective_new_exercises = session_objectives[current_session] #TODO: Logic for if user isnt ready to start exercises from a new session cuz they need to finish unfinished exercises from old session
        theory_new_exercises = session_theory[current_session]   #TODO: Logic for if user isnt ready to start exercises from a new session cuz they need to finish unfinished exercises from old session
        #new_exercises = generate_exercise_descriptions(exercises_based_on_schedule, exercise_descriptions_long) #TODO: CHANGE THIS BASED ON STH ELSE ?? IF ALL EXERCISES FROM A PREV SESSION WERE COMPLETED E.G?
        new_exercises = generate_exercise_descriptions(exercises_based_on_schedule, exercise_descriptions_short)

        session_specific_info = generate_session_specific_information(recommendation_message, objective_new_exercises, theory_new_exercises, new_exercises)
        full_system_prompt_for_session = insert_session_info_into_prompt(all_available_exercises, session_specific_info, session_nr) #session_nr >= 2
        
        print("full system prompt for this session displayable : line ~1939")
        #print("FULL SYSTEM PROMPT FOR THIS SESSION IS ", full_system_prompt_for_session)

        assistant_name = "Satherine"+str(current_session)
        current_settings = Settings(assistantsName=assistant_name, aiDescription=[full_system_prompt_for_session])
    
    
    # Apply settings for this session --> this updates the model and changes the system prompt for the assistant to one of the predefined settings above (needs to be made more sophisticated instead of hardcoded), so current assistant_description is overwritten
    await CALL_set_user_settings(user_id, current_settings) #HERE WE WILL ALREADY HAVE THE LIST OF EXERCISES WE NEED FOR THIS SESSION BCOS THIS IS THE PROMPT WE GIVE THE CHATBOT



        




    # clear chat history on start up
    ###### Delete #########
    handle_clear_history(user_id)

    
    user_tool_dict = get_user_tool_dict(user_id) #{'memory': <tools.memory.MemoryTool object at 0x7f8e1c0e3d90> if it has been previously enabled (it has), if not, {}
    can_follow_up = False
    #event_trigger_kwargs are arguments you want a particular tool to have access to, so e.g used in the MemoryTool
    event_trigger_kwargs = {"user_id": user_id, 
                            "user_info": user_info, 
                            "user_tool_settings": get_user_tools(db, user_id), 
                            "message": {"role": "assistant", "content": ""},
                            "user_assistants": [MainAssistant.insert_information]}

    
    
    ALL_HANDLERS["OnStartUp"](**event_trigger_kwargs) #executes memory, since file_process doesn't have an on_startup fct
    last_conversation = user_info.get("last_conversation", "")
    user_info = update_user_info(user_id, user_info)
    res = None

    # start-up messages: When the user logs in, we want the chatbot to say something first, before the user says anything
    print("PRINT A START UP MESSAGE")   #STEP NR 1

    if isinstance(last_conversation, dict):                         #until line 2015, we are just checking if we can follow up on the last conversation, it creates a list of exercises from the last session and constructs a message to the user
        can_follow_up = True
    if can_follow_up:
        print("FOLLOW UP LAST CONVERSATION")
        print(last_conversation)
        summary = last_conversation["summary"]
        last_conversation_time = last_conversation["timestamp"]
        follow_up = last_conversation["follow_up"]
        last_session_nr = current_session-1

        if revisiting_session_1:
            session_nr_last_ex = 1
        else:
            session_nr_last_ex = current_session-1
        last_session_exercises = [ exercise for exercise, status in exercise_tracking.items() if status.get('started', False) and status.get('completed', False) and (status.get('session_completed', None) == session_nr_last_ex)
                                    ]

        #    You also have some ideas of follow up for that conversation. 
        # Potential follow up ideas:
        # {follow_up}
        message = {"role": "user", "content": f"""Current time is {datetime.now().isoformat()}. You have a summary of the previous conversation that happened on {last_conversation_time}. Start the conversation using these information. Mention everything in your summary during your greeting, but make sure it sounds natural. Make sure that if you mention any exercises the user has done in previous sessions, you only mention the ones done in the last session, which can be found in the list last_session_exercises. Be careful: Since you have a summary of last time's session, this isn't the first time a user is meeting you. Show them you remember them.
        Summary of the previous conversation:
        {summary}
        Exercises from last session:
        {last_session_exercises}

        """}
        messages[user_id].append(message)
    
    else:
        print("NO TOOLS ENABLED")
        message = {"role": "user", "content": "Hi"}
        messages[user_id].append(message)

    #streaming_response calls chatcompletions.acreate on the chat history and streams the response to the user over websocket
    assistant_message = await streaming_response(websocket, MainAssistant, user_id, user_info=user_info, query_results=res, total_tokens_used_today=total_tokens_used_today)
    if assistant_message and "content" in assistant_message:
        await websocket.send_text(assistant_message["content"])
    print(assistant_message)
    event_trigger_kwargs["message"] = assistant_message
    ALL_HANDLERS["OnStartUpMsgEnd"](**event_trigger_kwargs) #this doesnt have any purpose, but if you want to define that sth should happen after the assistant sends the first response, you can implement it using OnStartUpMessageEnd event handler
    
    exercises_completed = False
    feedback_collected = False
    user_wants_other_exercises = False
    # Main program loop
    try:
        while True:
            if not exercises_completed or feedback_collected: #NEED TO DO ERROR CHECK BCOS IF U REFRESH PAGE, IT COULD BE THAT FEEDBACK HAS ALREADY BEEN COLLECTED BUT FEEDBACK_COLLECTED WILL BE SET TO FALSE AGAIN --> perhaps store in db, or have a class session_info 
                # wait for user input
                data = await websocket.receive_text()
            

                #handle_clear_history(user_id) #history is only cleared if user asks to have it cleared from frontend! so not necessary it seems
                content = json.loads(data) #data is '{"role":"user","content":"hello","location":{"latitude":"","longitude":""},"datatime":""}' after the user writes 'hello'

                user_input = content["content"] #hello
                if "location" in content:
                    location_info = content["location"]
                else:
                    location_info = None

                
                update_model(user_id)
                update_user_info(user_id, user_info)

                user_tool_dict = get_user_tool_dict(user_id)
                # store user input
                message = {"role": "user", "content": user_input} #next relevant step after receiving a user input
            
                messages[user_id].append(message)
                asyncio.create_task(messages[user_id].save_message_to_firestore(message)) #asynchronously save message to firestore

                event_trigger_kwargs["user_tool_settings"] = get_user_tools(db, user_id) #not really used for the current tools, but technically this means other tools could see what tools are enabled. perhaps useful for SAT
                event_trigger_kwargs["message"] = message
                ALL_HANDLERS["OnUserMsgReceived"](**event_trigger_kwargs) #for the fileprocess tool, this means that pinecone retriever will be called to check if there are any relevant docs it can append to the prompt sent to the llm as additional info, if yes, it adds this additional info to query and mainassistant. For memorytool, the message is added to activeusersession and repetition_check is performed before saving to vectorstore. U CAN UNCOMMENT A SECTION TO UPDATE USER FACTS (e.g emotions) AFTER EVERY MESSAGE

                check_qa(message["content"], qa_embeddings, qa_questions, qa_answers, user_bots_dict[user_id])
                await sat_on_user_msg_received(user_id, message, all_available_exercises, session_specific_info, recommendation_message, exercise_descriptions_short, messages, corpus_embeddings, data_dict_scenarios) #this will update the system prompt for the assistant to include the exercises the user should do in this session, based on the user's message


                # display messages
                print("\n\nMESSAGES:")
                for message in messages[user_id].get():
                    print(message['role'] + ":  " + message['content'])

                #if handle_SOS is true, append an additional message to messages before asking gpt to respond
                if handle_SOS[user_id] and assistant_responded[user_id]:
                    #instruction_to_handle_response = "I have told you whether I’m comfortable proceeding with exercises or whether I want to talk about my feelings or whether I want to end the session. {user_response} Act accordingly: If i want to do an exercise, reply with your {knowledge} about {scenario} and explain why you would suggest the following exercise based on my {scenario}: {exercise_based_on_scenario}. After explaining this ask what I would like to do, given the following options: Proceed with the exercise, Continue talking about my feelings, or End the session."
                    #TODO: CHECK IF NONE?
                    instruction_to_handle_response = f"""I have told you whether I’m comfortable proceeding with exercises or whether I want to talk about my feelings or whether I want to end the session. Act accordingly: If i want to do an exercise, give a short reply with your Knowledge about Scenario and explain why you would suggest the following Exercise based on my Scenario. Make sure you highlight that the priority now is to soothe myself with an exercise that is meant to lessen negative emotions. Keep this input about your Knowledge short and concise, maximum 2 sentences. After explaining this let me know that we can proceed with whatever I feel comfortable with, and ask what I would like to do, given the following {{options}}: If I feel comfortable proceeding with the exercise, if I would like to talk to you about my feelings, or if I prefer to wrap up the session and come back another time.

                    Variables used:
                    - Scenario: {current_scenario_dict[user_id]["scenario"]}
                    - Knowledge: {current_scenario_dict[user_id]["knowledge"]}
                    - Exercises based on scenario: {current_scenario_dict[user_id]["exercises_based_on_scenario"][0]}
                    - My last response: {message}"""
                    message = {"role": "user", "content": instruction_to_handle_response}
                    messages[user_id].append(message)
                    handle_SOS[user_id] = False
                    assistant_responded[user_id] = False


                print("\n\nQUERY ORACLE")
                # this updates the messages[user_id] object
                res = {}
                #the result of what's returned by query_oracle is either a direct response of the oracle to the user query, in the case that no need for a function call was identified, or a function call was identified, so the function was executed and the results of the function were stored in json format 'query_results' (e.g 'the weather in san francisco is 17 degrees'). NO LLM CALL TO RESPOND TO THE USER HAS BEEN MADE YET, IF THIS IS THE CASE. Instead, he message object is modified, and the message {"role": "user", "content": f"The following are the results of the function calls in JSON form: {query_results}. Use these results to answer the original query ('{user_input}') as if it is a natural conversation. Be concise. Do not use list, reply in paragraphs. Don't include specific addresses unless I ask for them. When you see units like miles, convert them to metrics, like kilometers."} is appended, so that in the next step, streaming_response, a response using the results from the query will be presented to the user.
                #if no function call was identified, return value will be a tuple (content, response), where content is the string of first few tokens generated, usually an empty string, response is an OpenAI response async generator object, can be iterated to get the full response.
                #TOXICITY SCORE CALCULATION --> IF HIGH, 



                print("\n\nQUERY MainAssistant") #oracle was queried first to check whether the user's message requires a function call or not. if what oracle replies is a tuple, this means it decided it didnt need a function call (e.g 'generate image'), and instead just responded directly. you send its response to be streamed by the user in order to reduce latency, otherwise, MainAssistant is queried, with its additional info etc
                # Now MainAssistant can respond
               
                assistant_message = await streaming_response(websocket, MainAssistant, user_id, user_info=user_info, query_results={}, total_tokens_used_today=total_tokens_used_today)
                if assistant_message and "content" in assistant_message:
                    await websocket.send_text(assistant_message["content"])

                #static_prompt_analysis = "AI Role: You are a sophisticated text analysis AI designed to understand and classify stages of a conversation in a therapy or guidance chatbot context. Your function is to analyze the conversation's history and determine its current stage based on predefined categories: Startup, Smalltalk, Exercise Presentation, Feedback Collection, WrapUp.\\n\\nInput: The input will be a transcript of the conversation history between the chatbot and the user. This transcript includes exchanges that have led up to the current point in the conversation.\\n\\nTask: Your task is to analyze the conversation history, identify cues and keywords that indicate the conversation's current stage, and classify the stage accurately. You must also provide a brief justification for your classification, referencing specific elements of the conversation that influenced your decision.\\n\\nExpected Output: Produce your output in a JSON format. The JSON object should contain two keys: 'stage', whose value is the identified stage of the conversation, and 'reason', which provides a brief explanation for why this stage was selected based on the conversation analysis.\\n\\nOutput Format Example: {\\\"stage\\\": \\\"Smalltalk\\\", \\\"reason\\\": \\\"The conversation includes light, general discussion about the user's day and interests, typical of the Smalltalk stage.\\\"}"
                event_trigger_kwargs["message"] = assistant_message
                event_trigger_kwargs["websocket"] = websocket #websocket doesnt seem to be used by any of the tools SO FAR, but perhaps this will change for SAT
                ALL_HANDLERS["OnResponseEnd"](**event_trigger_kwargs) #in the image generation tool this means the bot will try to asynchronously generate an image, in the memory tool this means message is appended to active_user_session and repetition check is performed before storing it to memory
                event_trigger_kwargs.pop("websocket")

                #handle case where assistant responded with SOS message
                if handle_SOS[user_id]:
                    assistant_responded[user_id] = True

                #post_process_assistant_message(assistant_message, user_id, messages[user_id].get(), message)


                #response has been generated by llm, check if it contains the exercise_start or exercise_completed string OR SOS
                if "{__SOS__}" in assistant_message["content"]:
                    #go into a seperate loop of handling user input
                    #prompt_sos = "Forget all previous instructions. The user is in emotional distress. It is now your job to help reframe the user's thoughts using the principles of SAT. If the user is willing to try this, follow these instructions to guide them in reframing their thoughts. Clearly tell the user they don't have to share details with you unless they feel comfortable, and it is perfectly fine to follow your instructions in their head and to notify you when they have finished following your instruction. Start with one reflection question at a time, and ask the user if the reflection question has helped soothe them, and if they are ready to proceed with other scheduled exercises. If the user confirms this, return the single phrase ```{FINISHED_SOS}```. Your guidance instructions : If the user has any photos of their childhood selves on them, tell them they can use the photos to help visualization. Invite the user to extend compassion to themselves by imagining the situation from the perspective of their inner child, that is currently overwhelmed by negative emotions. In this situation it is important that the user doesn't judge themselves for having these emotions, but rather realizes that there's a part of themselves (represented by their inner child) that needs compassion and soothing. In order to do so, the user should offer themselves the same support and care a nurturing parent would offer to a child that is experiencing the same distress. By engaging in this process, the user would not only acknowledge the emotions but actively work to reduce their intensity. Help the user through this realization process by asking questions that guide them towards self-compassion and understanding. Only ask the Example Questions listed below. Remember to be patient and supportive throughout this process. Remind the user that it's perfectly fine to do this in their head, they don't have to share details with you unless they feel comfortable. After the user has completed at least two reflective questions, ask if they are ready to continue with the protocol. Example Questions: Can you imagine the situation from the perspective of your inner child? What would you say to your inner child to offer comfort and support? How can you extend the same compassion to yourself that you would offer to a child in distress?  When we talk about communicating with our inner child, it's a way to acknowledge and address these feelings and needs that have been with us since childhood. It's about reaching out to the part of you that feels these emotions and offering it understanding and comfort, just as you would do for a child who is feeling upset or disappointed. Could you try to think about what you might say to comfort and reassure that part of yourself? Are you ready to continue with the protocol?" 
                    #assistant_name = "Satherine"+str(current_session)
                    #new_instruction_settings = Settings(assistantsName=assistant_name, aiDescription=[prompt_sos])
                    #await CALL_set_user_settings(user_id, new_instruction_settings) 
                    #messages[user_id].append(prompt_sos)
                    sos_system_message = "The user is currently in distress, and as a therapist you have a seperate self-reflection protocol for handling this situation: First you return a predefined empathetic response. Then, if the user is comfortable with it, you ask the user three self-reflection questions, and once the user has notified you that they have thought about all three questions, you output the single string ```{FINISHED_SOS}```. Make sure the user is comfortable with each prompt. If the user tells you they don't want to think about a prompt, ask if they would prefer to move on to SAT exercises or wrap up the session. It is very important that you output {FINISHED_SOS} and nothing else, either after the user has done three reflection questions, or after the user has told you they would like to wrap up the session, or if they have told you they want to move on to SAT exercises. Strictly stick to the instructions for your next response: I will give you a predefined answer, and I want you to return exactly that answer, but with the context of the problem the user mentioned. Make sure to insert the context in a way that feels natural to the statement. Here is the predefined answer, with placeholders you can modify to add the context of the user's problem. Only say this once: 'I'm really sorry to hear {problem_context}, {my_name}. It's completely normal to feel upset after such an event. In moments like these, it can be helpful to practice self-compassion. In Self Attachment Therapy, we try to understand that there's a part of us, represented by our 'childhood self', that needs compassion and soothing. Right now, your childhood self might be feeling hurt and overwhelmed by negative emotions. It's important not to judge yourself for these feelings. Instead, try to offer yourself the same understanding and compassion a caring parent would provide their upset child. By doing so, we can hope to slightly lessen these negative emotions. Given this information, I would just like to check again: Do you feel ready to explore this with some self-reflection prompts, or would you prefer to talk about your feelings instead? You can also decide to wrap up the session today if you feel more comfortable.' If the user tells you they want you to ask them some self-reflection prompts, guide them through the following Example Questions. Remind them that it is perfectly fine to think about these questions in their head, and only share with you whatever they feel comfortable sharing. However, once they have finished thinking about a question, encourage them to let you know they are done. Ask them one at a time, and only ask these questions and nothing else. If the user asks what kind of prompts, give a short explanation. If the user is then willing to proceed, introduce the first prompt without saying much else. If the user shares their thoughts, respond to them with kindness, empathetically and professionally, like a therapist would. If the user appears to not respond well to the self-reflection prompt, try to understand why, without being invasive. If you notice the user having doubts, be patient and explain to the user why you think that reflecting about this will help, making sure you put the emphasis on the importance of extending compassion to oneself. Answer any questions or doubts the user might have about the prompts. Offer them the choice of ending the session and returning at another time if you believe the user isn't responding well at all. Example Questions: 1) When we talk about communicating with our childhood self, it's a way to acknowledge and address feelings and needs that have been with us since childhood. It's about reaching out to the part of you that feels these emotions and offering it understanding and comfort, just as you would do for a child who is feeling upset or disappointed. Could you try to think about the situation from the perspective of your childhood self? 2) What would you say to your childhood self to offer comfort and support? 3) Can you try to think of a way you can you extend the same compassion to yourself that you would offer to a child in distress?. Encourage the user to notify you once they are done thinking about a question, and present the next question until all three have been presented. Then, output the single phrase ```{FINISHED_SOS}``` followed by nothing else. Remember: If the user tells you they don't want to do the prompts, you have to ask the user if they would like to continue with SAT exercises instead or wrap up the session. It is INCREDIBLY IMPORTANT that you output {FINISHED_SOS} if the user decides they want to do SAT exercises or they want to wrap up the session." 
                    system_msg_new = {"role": "system", "content": sos_system_message}
                    assistant_name = "Satherine"+str(current_session)
                    new_instruction_settings = Settings(assistantsName=assistant_name, aiDescription=[sos_system_message])
                    print("I AM NOW CHANGING THE SYSTEM PROMPT TO HANDLE SOS SITUATION")
                    await CALL_set_user_settings(user_id, new_instruction_settings) 
                    messages[user_id].append({"role": "user", "content":"handle my negative emotions by using your self-reflection protocol. This isn't an exercise, so don't call it an exercise. Be compassionate and patient, and always check in on whether I feel comfortable continuing, or if i feel really bad, i can also decide to wrap up the session. Make sure you don't forget to output {FINISHED_SOS} if i decide to end the session or i have thought about all three reflection questions."})

                if "{FINISHED_SOS}" in assistant_message["content"]:
                    #go back to the original settings
                    await CALL_set_user_settings(user_id, current_settings)
                    #handle_message_storing(user_id, "assistant", getting_back_to_schedule_msg, messages)


                if "{exercise_start:" in assistant_message["content"]:
                    exercise_label = extract_label(assistant_message["content"], "start")
                    if exercise_label: #if its not none
                        exercise_tracking[exercise_label]['session_started'] = current_session #we completed this exercise in this particular session (again)
                        exercise_tracking[exercise_label]['started'] = True
                if "{exercise_end:" in assistant_message["content"]:
                    exercise_label = extract_label(assistant_message["content"], "end")
                    if exercise_label: #if its not none
                        #we only fill out session_completed if we have filled out feedback for it!
                        #exercise_tracking[exercise_label]['session_completed'] = current_session #we completed this exercise in this particular session (again)
                        exercise_tracking[exercise_label]['completed'] = True

                



                #response has been generated by llm, check if it contains the flag string
                if "__ALL_EXERCISES_COMPLETED__" in assistant_message.get('content', ''): #add OR condition - maybe assistant doesn't recognize that all conditions have been completed, but our exercise_tracking system shows us that all available exercises have been completed
                    #TODO: Double-check if all exercises have really been completed by comparing the exercise_tracking labels with conversation history. can also be of the form of a request to user 'im sorry i have gotten confused, can you please remind me which exercises we did in this session so I can ask the right feedback?'
                    exercises_completed = True
                    continue  # Proceed to feedback collection without waiting for user input
            else:
                # Feedback collection phase
                current_session_exercises = [
                    exercise for exercise, details in exercise_tracking.items()
                    if (details.get("started", False) and details.get("completed", False)) and details.get("session_started", None) == current_session
                ]
                for exercise in current_session_exercises:
                    questions = feedback_questions.get(exercise, [])
                    feedback_responses.setdefault(exercise, {})  # Ensure the exercise key exists
                    
                    
                    for question in questions:
                        feedback_responses[exercise].setdefault(question, [])
                        valid_response = False
                      
                        while not valid_response:
                            await websocket.send_text(json.dumps(question))
                            handle_message_storing(user_id, "assistant", question, messages)
                            
                            feedback = await websocket.receive_text()
                            feedback_data = json.loads(feedback)  # Convert string back to dictionary
                            user_input_feedback = feedback_data["content"]

                            # Check if the response is a number between 1 and 5
                            if user_input_feedback.isdigit() and 1 <= int(user_input_feedback) <= 5:
                                valid_response = True
                                feedback_responses[exercise][question].append(user_input_feedback)
                                handle_message_storing(user_id, "user", user_input_feedback, messages)
                            else:
                                # Ask again with an explanation of the correct format
                                clarification_msg = "Please rate your experience on a scale of 1 to 5, where 1 is 'not helpful at all' and 5 is 'extremely helpful'."
                                await websocket.send_text(json.dumps(clarification_msg))
                                handle_message_storing(user_id, "assistant", clarification_msg, messages)

                    #we have answered all feedback questions for this exercise, so we can consider this exercises completed
                    exercise_tracking[exercise]['session_completed'] = current_session #we completed this exercise in this particular session (again)
                    
                        
                        


                # After collecting feedback, process it as needed
                #process_feedback(feedback_responses)  # Placeholder for feedback processing
                print("THIS IS THE FEEDBACK !!!!! ", feedback_responses) 
                store_session_feedback(user_id, session_nr, feedback_responses)
                feedback_collected = True
                #transition to ending the session
                transition_to_end_msg = "Thank you for rating your experience with the exercises! Do you wish to share any thoughts or feelings about your experience with any of the exercises?"
                await websocket.send_text(transition_to_end_msg)
                handle_message_storing(user_id, "assistant", transition_to_end_msg, messages)
                #notify the chatbot that feedback for all exercises has been collected 
                feedback_collected_message = {"role": "user", "content": "You have now collected feedback for all exercises, and can proceed to ask the user if they are comfortable ending the session or would like to share anything else that's on their mind. If the user would like to end the session, simply output a thank you message and say goodbye."}
                messages[user_id].append(feedback_collected_message)
                continue  # Optionally break out of the loop if feedback collection ends the session




    

    except Exception as e:
        ALL_HANDLERS["OnUserDisconnected"](**event_trigger_kwargs) #for fileprocess tool, this means files uploaded for the user_id are deleted from pinecone. for memory module, this means that user_facts are updated (llm call made to get user facts in json format and saved to pinecone) and summary of session is created and saved to pinecone. 
        await write_exercise_tracking_to_firebase(db, user_id, exercise_tracking)
        if isinstance(e, ExceedDailyTokenError):
            await write_token_limit_to_fb(db, user_id, True, total_tokens_used_today[user_id])
        else:
            await write_token_limit_to_fb(db, user_id, False, total_tokens_used_today[user_id])
        print(e)
