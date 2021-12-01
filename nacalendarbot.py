import configparser
import datetime
import logging
import os
import re
import time

from datetime import timezone

import praw
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# configure script logging
logging.basicConfig(level=logging.INFO)

# Configuration constants
COMMON = 'Common'
REDDIT = 'Reddit'
GOOGLE = 'Google'

# Reddit client - use to manipulate Reddit.
class RedditClient:

    def __init__(self, client_id, client_secret, username, password, user_agent, subreddit):
        self.client_id = client_id
        self.client_secret = client_secret
        self.username = username
        self.password = password
        self.user_agent = user_agent
        self.subreddit = subreddit

    @classmethod
    def fromFile(cls, filename):
        config = configparser.ConfigParser()
        config.read(filename)
        return cls(
            config.get(REDDIT, 'client_id'),
            config.get(REDDIT, 'client_secret'),
            config.get(REDDIT, 'username'),
            config.get(REDDIT, 'password'),
            config.get(REDDIT, 'user_agent'),
            config.get(COMMON, 'subreddit')
        )

    def release(self):
        self.client_id = self.client_secret = self.username = self.password = self.user_agent = \
            self.subreddit = None

    # authenticate bot to reddit
    # NOTE: this authentication logic will break if you turn 2FA on for your reddit account.
    # TODO: code for additional scopes.  See https://praw.readthedocs.io/en/latest/tutorials/refresh_token.html
    def authenticate(self):
        logging.info("Trying to access reddit...")
        reddit = praw.Reddit(
            client_id=self.client_id,
            client_secret=self.client_secret,
            username=self.username,
            password=self.password,
            user_agent=self.user_agent
        )
        logging.info("Authenticated!")
        return reddit

    # retrieve submissions
    def get_submissions(self, reddit):
        # grab our subreddit
        neon_anarchy = reddit.subreddit('NeonAnarchy')
        return neon_anarchy.new(limit=20)

    # translate submission to job
    def to_job(self, submission):
        # process the post

        # Create job.
        new_job = Job(
            post_id=submission.id,
            author=submission.author.name,
            title=submission.title,
            selftext=submission.selftext,
            url=submission.url,
            permalink=submission.permalink,
            created_utc=submission.created_utc,
            flair=submission.link_flair_text,
            edited=submission.edited
        )

        # log it!
        logging.debug(str(vars(new_job)))
        return new_job

    # Post comment in submission
    def post_comment(self, submission, text):
        try:
            own_comment = self.find_own_comment(submission)

            # If comment exists, update comment text
            if own_comment:
                if (text != own_comment.body):
                    own_comment.edit(text)
                    logging.info("Edited comment on: " + submission.title)
                else:
                    logging.info("No change to comment - not updating.")

            # else, add comment
            else:
                submission.reply(text)
                logging.info("Commented on: " + submission.title)

        except Exception as e:
            logging.warning("Could not comment in submission: " + submission.title)
            logging.exception(e)

    # Find comment posted by the bot
    def find_own_comment(self, submission):
        # Find own comment in submission comment tree (if exists)
        for comment in submission.comments:
            if comment.author and comment.author.name == self.username:
                return comment
        return None


class Job:

    def __init__(self, title=None, post_id=None, author=None, selftext=None, url=None, permalink=None, created_utc=None,
                 flair=None, edited=None):
        self.title = title
        self.post_id = post_id
        self.author = author
        self.selftext = selftext
        self.url = url
        self.permalink = permalink
        self.created_utc = created_utc
        self.flair = flair
        self.edited = edited

        try:
            self.metaplot, self.name_of_run, self.year, self.month, self.day, self.hour, self.minute, self.timezone = \
                Job.parse_title(title)
        except Exception:
            logging.debug('unable to parse title: ' + title)
            self.metaplot, self.name_of_run, self.year, self.month, self.day, self.hour, self.minute, self.timezone = \
                Job.parse_selftext(selftext)

    # getter - handle None values
    def get_flair(self):
        if (self.flair is None):
            return 'JOB FLAIR?'
        else:
            return self.flair

    @classmethod
    def parse_title(cls, title):
        logging.debug('parse title: ' + title)

        # Format is supposed to be: '[Metaplot, if any] Name of Run. Year-Month-Day. Time UTC'
        # Actual format is all-over-the-place.  Humans - bah!  Anchor on the date component, and go from there.
        # To cater for this, I've put in an extensible parsing mechanism to cater for completely different regex's.

        parsers = {
            '(.+?)(\d{4})[-\.\s]+(\d{1,2})[-\.\s]+(\d{1,2})(.*)': Job.parse_anchor_on_short_date,
            '(.+?)(\d{1,2})[-\.\s]+(\d{1,2})[-\.\s]+(\d{4})(.*)': Job.parse_anchor_on_short_date_reversed,
        }

        for key, value in parsers.items():
            p = re.compile(key)
            m = p.match(title)
            if m:
                result = value(m)
                if result is not None:
                    return result

        # no match
        raise Exception('Unable to parse time/date in title: ' + title)

    @classmethod
    def parse_selftext(cls, selftext):
        logging.debug('parse selfText: ' + selftext)

        # Find calendar hint: {CALENDAR_HINT: <Title>}
        m = re.search('.*{CALENDAR.*HINT:(.*)}.*', selftext, re.MULTILINE)
        if m:
            hint = m.group(1)
            logging.debug('found hint: ' + hint)
            return Job.parse_title(hint)

        # no match
        raise Exception('Unable to find/parse calendar hint in selfText.')

    @classmethod
    def parse_name_fragment(cls, name_fragment):
        # look for optional metaplot.  If not found - the whole thing is a name.
        p = re.compile('\[(.*?)\](.*)')
        m = p.match(name_fragment)
        if m:
            return m.group(1).strip(), m.group(2).strip()
        else:
            return '', name_fragment.strip()

    @classmethod
    def parse_time_fragment(cls, time_fragment):
        # Look for 'HHMM Timezone', 'HMM Timezone', 'HH:MM Timezone' or 'H:MM Timezone'.  In all cases, Timezone optional
        m = re.compile('[^\d]*(\d{1,2}):?(\d\d)\s+?([\w/]+).*').match(time_fragment)
        if m:
            return int(m.group(1)), int(m.group(2)), m.group(3).strip()

        # No timezone
        m = re.compile('[^\d]*(\d{1,2}):?(\d\d)[^\d]*').match(time_fragment)
        if m:
            return int(m.group(1)), int(m.group(2)), 'UTC'

        # unable to parse
        raise Exception('Unable to parse time fragment: ' + time_fragment)

    @classmethod
    # time = 'year-month-day' or 'year.month.day'
    def parse_anchor_on_short_date(cls, m):
        metaplot, name_of_run = Job.parse_name_fragment(m.group(1))
        year = int(m.group(2))
        month = int(m.group(3))
        day = int(m.group(4))
        hour, minute, timezone = Job.parse_time_fragment(m.group(5))
        return metaplot, name_of_run, year, month, day, hour, minute, timezone

    @classmethod
    # time = 'day-month-year' or 'day.month.year'
    def parse_anchor_on_short_date_reversed(cls, m):
        metaplot, name_of_run = Job.parse_name_fragment(m.group(1))
        day = int(m.group(2))
        month = int(m.group(3))
        year = int(m.group(4))
        hour, minute, timezone = Job.parse_time_fragment(m.group(5))
        return metaplot, name_of_run, year, month, day, hour, minute, timezone

    # Return datetime object representing internal date/time state.
    # TODO: this will always ignore the timezone value and will hardcode UTC.  Expand!
    def get_start_datetime(self):
        return datetime.datetime(self.year, self.month, self.day, self.hour, self.minute, 0, 0, tzinfo=timezone.utc)


# Google client - use to manipulate Google's calendar.
class GoogleClient:
    # Bot needs to manipulate events, right?
    CALENDAR_SCOPES = ['https://www.googleapis.com/auth/calendar.events']

    # Google's using ISO date/time format.
    DATE_TIME_FORMAT = "%Y-%m-%dT%H:%M:00"

    def __init__(self, calendar_id, calendar_public_url, calendar_docs_url, creator, subreddit):
        self.calendar_id = calendar_id
        self.calendar_public_url = calendar_public_url
        self.calendar_docs_url = calendar_docs_url
        self.creator = creator
        self.subreddit = subreddit
        self.service = None

    def release(self):
        self.calendar_id = self.calendar_public_url = self.calendar_docs_url = self.creator = self.subreddit = \
            self.service = None

    @classmethod
    def fromFile(cls, filename):
        config = configparser.ConfigParser()
        config.read(filename)
        return cls(
            config.get(GOOGLE, 'calendar_id'),
            config.get(GOOGLE, 'calendar_public_url'),
            config.get(GOOGLE, 'calendar_docs_url'),
            config.get(GOOGLE, 'creator'),
            config.get(COMMON, 'subreddit')
        )

    # retrieve or generate credentials
    def credentials(self, credentials_file):
        """Shows basic usage of the Google Calendar API.
        Prints the start and name of the next 10 events on the user's calendar.
        """
        creds = None
        # The file credentials.json stores the user's access and refresh tokens, and is
        # created automatically when the authorization flow completes for the first
        # time.
        if os.path.exists('token.json'):
            creds = Credentials.from_authorized_user_file('token.json', GoogleClient.CALENDAR_SCOPES)
        # If there are no (valid) credentials available, let the user log in.
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(credentials_file, GoogleClient.CALENDAR_SCOPES)
                creds = flow.run_local_server(port=0)
            # Save the credentials for the next run
            with open('token.json', 'w') as token:
                token.write(creds.to_json())

        # return
        return creds

    # authenticate bot to google
    def authenticate(self, creds):
        self.service = build('calendar', 'v3', credentials=creds)
        return self.service

    # Create an event block
    def build_event_json(self, job):
        # Builds the JSON block for Google from the Job contents
        start_datetime = job.get_start_datetime()
        end_datetime = start_datetime + datetime.timedelta(hours=3)  # TODO - parse run length from the run text, maybe.

        eventJson = {
            'summary': '[' + job.get_flair().upper() + ']' + " " + job.title,
            'location': 'https://reddit.com/r/' + self.subreddit,
            'description': 'https://reddit.com' + job.permalink + ' by ' + job.author,
            'start': {
                'dateTime': start_datetime.strftime(GoogleClient.DATE_TIME_FORMAT),
                'timeZone': job.timezone
            },
            'end': {
                'dateTime': end_datetime.strftime(GoogleClient.DATE_TIME_FORMAT),
                'timeZone': job.timezone
            },
            'extendedProperties': {
                # Allow us to search on event given reddit post id.
                'private': {
                    'redditPost': job.post_id
                },
                'shared': {
                    'createdBy': self.creator
                }
            }
        }
        return eventJson

    # insert event into Calendar
    def create_event(self, job):
        logging.debug('creating event for post_id: ' + str(job.post_id))
        eventJson = self.build_event_json(job)
        response = self.service.events() \
            .insert(calendarId=self.calendar_id, body=eventJson).execute()
        logging.debug('Response: ' + str(response))

    # find event in calendar using the private properties properties.
    def find_all_events(self, post_id):
        logging.debug('finding all events for post_id: ' + str(post_id))
        events_response = self.service.events().list(calendarId=self.calendar_id,
                                                     privateExtendedProperty='redditPost=' + str(post_id)).execute()
        logging.debug('Response: ' + str(events_response))
        events = events_response.get('items', [])
        # TODO - error handling
        return events

    # find event in calendar using the private properties properties.
    def find_event(self, post_id):
        logging.debug('finding event for post_id: ' + str(post_id))
        events = self.find_all_events(post_id)
        if events is not None and len(events) > 0:
            return events[0]
        else:
            return None

    # Update event (if required)
    def update_event(self, event, job):
        # Event ID
        event_id = event['id']

        # Check to see if event has changed.  Check for flair change or start change.
        # TODO - "not in" instead of != as google adds Z (Zulu/local).  I might have coded incorrectly in GoogleClient.authenticate() - though it works.  Check.
        is_changed = \
            job.get_flair().upper() not in event['summary'] or \
            job.get_start_datetime().strftime(GoogleClient.DATE_TIME_FORMAT) not in event['start']['dateTime'] or \
            job.timezone not in event['start']['timeZone']

        # If something's changed, go ahead and update the calendar event.
        if (is_changed):
            logging.info("Updating event: " + event_id)
            eventJson = self.build_event_json(job)
            response = self.service.events() \
                .update(calendarId=self.calendar_id, eventId=event_id, body=eventJson).execute()
            return response

        # No need to update.
        logging.info('Updating event: ' + event_id + ' skipping event update - no change required.')
        return None

    # find all events with the given post_id and delete it
    def delete_event(self, post_id):
        # find event(s)
        events = self.find_all_events(post_id)
        logging.debug('event: ' + str(events))

        # delete them - clean out any duplicates if found (from bot failures, dodgy data, etc).
        if events is not None:
            for event in events:
                logging.debug('deleting event for post_id: ' + str(post_id))
                response = self.service.events(). \
                    delete(calendarId=self.calendar_id, eventId=event['id']).execute()
                logging.debug('response: ' + str(response))


# Google client - use to manipulate Google's calendar.
class NeonAnarchyCalendarBot:
    TEMPLATE_NOTIFICATION = """Your Job has been posted in the [Neon Anarchy Job Calendar]({calendar_public_url}). In discord, use the following tags to refer to the Job's scheduled time: <t:{run_time}:F> (absolute job date/time) and <t:{run_time}:R> (relative time until the job).   

Calendar bot post.  Any problems, please let /u/kajh know!  Bot [docs here]({calendar_docs_url})."""

    TEMPLATE_ERROR = """Hi {author}!  I encountered a problem - I was not able to add this job to the [Neon Anarchy Job Calendar]({calendar_public_url}).
    
*Problem:* {problem}

*Solution*: {solution}
    
Calendar bot post.  Any problems, please let /u/kajh know!  Bot [docs here]({calendar_docs_url})."""

    TEMPLATE_PARSE_PROBLEM = "I couldn't work out the title of your post as it didn't match the recommended format."
    TEMPLATE_PARSE_SOLUTION = "Please refer to [this sticky post](https://reddit.com/r/NeonAnarchy/comments/hjq4ji/example_run_metaplot_if_any_name_of_run/) for an example run post. " \
                              "The title needs to follow the specified format so that I can understand it.  " \
                              "Given we can't modify post titles, you can edit your post and put a calendar hint anywhere into the text of your job - cut/paste/modify the following: *{CALENDAR_HINT: [Metaplot, if any] Name of Run. 2021-08-16. 2300 UTC}*."

    TEMPLATE_GOOGLE_PROBLEM = "I got an error from Google Calendar when creating your event."
    TEMPLATE_GOOGLE_SOLUTION = "I'm not sure how to fix.  The error message I got from Google was: {message}"

    def __init__(self):
        self.redditClient = None
        self.redditService = None
        self.googleClient = None
        self.googleService = None

    def run(self):
        # Authenticate against Reddit
        try:
            logging.info('Authenticating to Reddit.')
            self.redditClient = RedditClient.fromFile('nacalendarbot.cfg')
            self.redditService = self.redditClient.authenticate()
        except Exception as e:
            logging.exception('unable to authenticate against Reddit', e)
            return

        # Authenticate against Google
        try:
            logging.info('Authenticating to Google.')
            self.googleClient = GoogleClient.fromFile('nacalendarbot.cfg')
            credentials = self.googleClient.credentials('credentials.json')
            self.googleService = self.googleClient.authenticate(credentials)
        except Exception as e:
            logging.exception('unable to authenticate against Google', e)
            return

        # read and process all jobs on Reddit
        try:
            logging.info('Reading jobs on NeonAnarchy.')

            # read submissions
            submissions = self.redditClient.get_submissions(self.redditService)
            for submission in submissions:

                # Skip if post is flaired 'Meta'.
                if (submission.link_flair_text is not None and 'META' in submission.link_flair_text.upper()):
                    logging.info('skipping meta-flaired post: ' + submission.title)

                    # Skip post
                    continue

                # Otherwise - process submission
                job = None
                try:
                    logging.info('processing submission: ' + submission.title)
                    job = self.redditClient.to_job(submission)
                    logging.debug('parsed_job = ' + str(vars(job)))

                except Exception as e:
                    logging.error('unable to parse submission: ' + submission.title + '. Error: ' + str(e))

                    # Post parse error to the thread.
                    self.redditClient.post_comment(submission,
                                                   NeonAnarchyCalendarBot.TEMPLATE_ERROR.format(
                                                       author='/u/' + submission.author.name,
                                                       calendar_public_url=self.googleClient.calendar_public_url,
                                                       problem=NeonAnarchyCalendarBot.TEMPLATE_PARSE_PROBLEM,
                                                       solution=NeonAnarchyCalendarBot.TEMPLATE_PARSE_SOLUTION,
                                                       calendar_docs_url=self.googleClient.calendar_docs_url)
                                                   )

                    # next submission
                    continue

                # Find and update/create event
                try:
                    logging.info('Finding event for submission: ' + submission.title)
                    event = self.googleClient.find_event(job.post_id)
                    if event:
                        logging.info('Event found for submission: ' + submission.title + '. Updating.')
                        self.googleClient.update_event(event, job)
                    else:
                        logging.info('No event found for submission: ' + submission.title + '. Creating.')
                        self.googleClient.create_event(job)

                except Exception as e:
                    logging.error(
                        'received error from google calendar apis: ' + submission.title + '. Error: ' + str(e))

                    # Post parse error to the thread.
                    self.redditClient.post_comment(submission,
                                                   NeonAnarchyCalendarBot.TEMPLATE_ERROR.format(
                                                       author='/u/' + submission.author.name,
                                                       calendar_public_url=self.googleClient.calendar_public_url,
                                                       problem=NeonAnarchyCalendarBot.TEMPLATE_GOOGLE_PROBLEM,
                                                       solution=NeonAnarchyCalendarBot.TEMPLATE_GOOGLE_SOLUTION.format(
                                                           message=str(e)),
                                                       calendar_docs_url=self.googleClient.calendar_docs_url)
                                                   )

                    # next submission
                    continue

                # Success! Post comment to Job thread with link to calendar.
                try:
                    job_start = job.get_start_datetime()
                    run_time = int(job_start.timestamp())

                    # Update or create the calendar notification post.
                    self.redditClient.post_comment(
                        submission, NeonAnarchyCalendarBot.TEMPLATE_NOTIFICATION
                            .format(calendar_public_url=self.googleClient.calendar_public_url,
                                    calendar_docs_url=self.googleClient.calendar_docs_url,
                                    run_time=run_time)
                    )

                except Exception as e:
                    logging.exception('error commenting back to reddit', e)

                # next submission
                continue

        except Exception as e:
            logging.exception('error reading NeonAnarchy jobs', e)
            return


# Bot main loop
if __name__ == '__main__':
    # Loop while running.
    while True:
        try:
            NeonAnarchyCalendarBot().run()
        except Exception as e:
            logging.exception('bot error', e)

        # go back to sleep for a few minutes
        seconds = (5 * 60)
        logging.info("Sleeping for " + str(seconds) + " seconds.")
        time.sleep(seconds)
