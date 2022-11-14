import datetime
import unittest

from calendarbot import RedditClient, GoogleClient, Job

# Test selectors for partial test runs
TEST_REDDIT = False
TEST_GOOGLE = False
TEST_PARSING = True


class RedditTestCase(unittest.TestCase):
    # reddit client - shared for all tests
    client = None
    reddit = None

    @classmethod
    def setUpClass(cls):
        cls.client = RedditClient.from_file('na/calendarbot.cfg')

    @classmethod
    def tearDownClass(cls):
        cls.client.release()
        cls.reddit = None

    @unittest.skipUnless(TEST_REDDIT, "do not test reddit authentication")
    def test_authenticate(self):
        RedditTestCase.reddit = RedditTestCase.client.authenticate()
        self.assertIsNotNone(RedditTestCase.reddit)

    @unittest.skipUnless(TEST_REDDIT, "Not retrieving submissions")
    def test_get_submissions(self):
        submissions = RedditTestCase.client.get_submissions(RedditTestCase.reddit)
        self.assertIsNotNone(submissions)

        # convert submissions to jobs
        num_read = num_scanned = num_errors = 0
        for submission in submissions:
            try:
                num_read += 1
                job = RedditTestCase.client.to_job(submission)
                self.assertIsNotNone(job)
                num_scanned += 1
            except Exception:
                # ignore errors - am sure the data is broken in at least one of the records
                num_errors += 1
                continue

        self.assertTrue(num_read >= num_scanned)


class GoogleTestCase(unittest.TestCase):
    # google client - shared for all tests
    client = None
    service = None

    @classmethod
    def setUpClass(cls):
        cls.client = GoogleClient.from_file('na/calendarbot.cfg')

    @classmethod
    def tearDownClass(cls):
        cls.client.release()
        cls.reddit = None
        cls.service = None

    @unittest.skipUnless(TEST_PARSING, "don't bother with parsing")
    def test_parse_title_good(self):

        # test dashes
        self.parse_and_compare_title('[Metaplot, if any] Name of Run. 2021-04-01. 1234 UTC', 'Metaplot, if any',
                                     'Name of Run.', 2021, 4, 1, 12, 34, 'UTC')
        self.parse_and_compare_title('Name of Run. 2021-04-01. 1234 UTC', '', 'Name of Run.', 2021, 4, 1, 12, 34, 'UTC')
        self.parse_and_compare_title('Name of Run. 2021-04-01. 234 UTC', '', 'Name of Run.', 2021, 4, 1, 2, 34, 'UTC')

        # test dots
        self.parse_and_compare_title('[Metaplot, if any] Name of Run. 2021.04.01. 1234 UTC', 'Metaplot, if any',
                                     'Name of Run.', 2021, 4, 1, 12, 34, 'UTC')
        self.parse_and_compare_title('Name of Run. 2021.04.01. 1234 UTC', '', 'Name of Run.', 2021, 4, 1, 12, 34, 'UTC')
        self.parse_and_compare_title('Name of Run. 2021.04.01. 234 UTC', '', 'Name of Run.', 2021, 4, 1, 2, 34, 'UTC')

        # test brackets and braces
        self.parse_and_compare_title('[Metaplot, if any] [Funky other thing] Name of Run. 2021-04-01. 1234 UTC',
                                     'Metaplot, if any', '[Funky other thing] Name of Run.', 2021, 4, 1, 12, 34, 'UTC')

        # test no separators
        self.parse_and_compare_title('[Metaplot, if any] Deacon Denied Redux 20220711 2359 UTC', 'Metaplot, if any',
                                     'Deacon Denied Redux', 2022, 7, 11, 23, 59, 'UTC')
        self.parse_and_compare_title('Deacon Denied Redux 20220711 2359 UTC', '', 'Deacon Denied Redux', 2022, 7, 11, 23, 59, 'UTC')
        self.parse_and_compare_title('Deacon Denied Redux 20220711 359 UTC', '', 'Deacon Denied Redux', 2022, 7, 11, 3, 59, 'UTC')

        # test no separators
        self.parse_and_compare_title('[Metaplot, if any] Deacon Denied Redux 11072022 2359 UTC', 'Metaplot, if any',
                                     'Deacon Denied Redux', 2022, 7, 11, 23, 59, 'UTC')
        self.parse_and_compare_title('Deacon Denied Redux 11072022 2359 UTC', '', 'Deacon Denied Redux', 2022, 7, 11, 23, 59, 'UTC')
        self.parse_and_compare_title('Deacon Denied Redux 11072022 359 UTC', '', 'Deacon Denied Redux', 2022, 7, 11, 3, 59, 'UTC')

        # test timezones
        self.parse_and_compare_title('Name of Run. 2021-04-01. 234 UTC.', '', 'Name of Run.', 2021, 4, 1, 2, 34, 'UTC')
        self.parse_and_compare_title('Name of Run. 2021-04-01. 234 Australia/Sydney', '', 'Name of Run.', 2021, 4, 1, 2,
                                     34, 'Australia/Sydney')
        self.parse_and_compare_title('Name of Run. 2021-04-01. 234 Australia/Sydney.', '', 'Name of Run.', 2021, 4, 1,
                                     2, 34, 'Australia/Sydney')

        # Reddit post data
        self.parse_and_compare_title('The Land of Mana-Storms and Spiders. 2021-08-11 0010', '',
                                     'The Land of Mana-Storms and Spiders.', 2021, 8, 11, 0, 10, 'UTC')
        self.parse_and_compare_title('297 Meters Under the Seas 2021-8-8 1:00 UTC', '',
                                     '297 Meters Under the Seas', 2021, 8, 8, 1, 0, 'UTC')
        self.parse_and_compare_title('Red Hot Cargo 21-08-2021 14:00 UTC', '',
                                     'Red Hot Cargo', 2021, 8, 21, 14, 0, 'UTC')
        self.parse_and_compare_title('The spice of life. 2021-8-13 1:00 UTC', '', 'The spice of life.', 2021, 8, 13, 1,
                                     0, 'UTC')
        self.parse_and_compare_title('The Manor in the Mountains. 2021 8-15 22:00 UTC', '',
                                     'The Manor in the Mountains.', 2021, 8, 15, 22, 0, 'UTC')

        # Variants for testing to see what it does!
        self.parse_and_compare_title('The Manor in the Mountains. 2021       8-15 22:00 UTC', '',
                                     'The Manor in the Mountains.', 2021, 8, 15, 22, 0, 'UTC')
        self.parse_and_compare_title('The Manor in the Mountains. 2021. .- . -- 8.15 22:00 UTC', '',
                                     'The Manor in the Mountains.', 2021, 8, 15, 22, 0, 'UTC')
        self.parse_and_compare_title('The Manor in the Mountains. 15. .- . -- 8.2021 22:00 UTC', '',
                                     'The Manor in the Mountains.', 2021, 8, 15, 22, 0, 'UTC')

    def parse_and_compare_title(self, title_string, metaplot, name_of_run, year, month, day, hour, minute, timezone):
        parsed_metaplot, parsed_name_of_run, parsed_year, parsed_month, parsed_day, parsed_hours, parsed_minutes, parsed_timezone = Job.parse_title(
            title_string)
        params = [metaplot, name_of_run, year, month, day, hour, minute, timezone]
        parsed = [parsed_metaplot, parsed_name_of_run, parsed_year, parsed_month, parsed_day, parsed_hours,
                  parsed_minutes, parsed_timezone]
        self.assertEqual(params, parsed)

    @unittest.skipUnless(TEST_PARSING, "don't bother with parsing")
    def test_parse_bad(self):
        parse_strings = [
            'This is complete crap.',
        ]
        for str in parse_strings:
            try:
                metaplot, name_of_run, year, month, day, hours, minutes, timezone = Job.parse_title(str)
                self.fail("Expected exception not thrown for title" + str)
            except Exception:
                continue

    # Search the selftext for a calendar hint.
    def parse_and_compare_selftext(self, selftext_string, metaplot, name_of_run, year, month, day, hour, minute,
                                   timezone):
        parsed_metaplot, parsed_name_of_run, parsed_year, parsed_month, parsed_day, parsed_hours, parsed_minutes, parsed_timezone = \
            Job.parse_selftext(selftext_string)
        params = [metaplot, name_of_run, year, month, day, hour, minute, timezone]
        parsed = [parsed_metaplot, parsed_name_of_run, parsed_year, parsed_month, parsed_day, parsed_hours,
                  parsed_minutes, parsed_timezone]
        self.assertEqual(params, parsed)

    @unittest.skipUnless(TEST_PARSING, "don't bother with parsing")
    def test_parse_selftext_good(self):
        self.parse_and_compare_selftext("""Blahblah...
{CALENDAR_HINT: The Land of Mana-Storms and Spiders. 2021-08-11 0010}
MoreBlahblah!""", '', 'The Land of Mana-Storms and Spiders.', 2021, 8, 11, 0, 10, 'UTC')
        self.parse_and_compare_selftext("""Blahblah...
{CALENDAR_HINT: The Land of Mana-Storms and Spiders. 2021-08-11 0010}
{CALENDAR_HINT: TWO HINTS - BAD SECOND!!!}
MoreBlahblah!""", '', 'The Land of Mana-Storms and Spiders.', 2021, 8, 11, 0, 10, 'UTC')
        self.parse_and_compare_selftext("""
players 4 to 5
duration 3 to 4hrs (can run over to 5 if needed)
communication discord, Roll 20 if wanted but not preped
in game  locations: Seattle for the meet and at sea for the action
difficulty medium
impromptu picks made 30 minuets pre run
&#x200B;
///////
Hey chummers we have a job for yall
ya see a pice of history fell to earth and i would like it unforunalty it crashed off the russian coast
so if you wouldent mind geting it for us i can reward you hansomly.
oh and we can provideing transport if needed
/////// -- J
caution this run will involve diveing basic gear will be provided and some tempory training but if you want anything customized bring your own
please post your discord name, a PDF of your char, career karma, last run (player).
IC prompt (what do you think the object is)
&#x200B;
&#x200B;
&#x200B;
 *{CALENDAR\_HINT: Kessler syndrome 1 (impromptu) 2021-08-15 19:00 UTC}* 
""", '', 'Kessler syndrome 1 (impromptu)', 2021, 8, 15, 19, 0, 'UTC')

    @unittest.skipUnless(TEST_PARSING, "don't bother with parsing")
    def test_parse_selftext_bad(self):
        parse_strings = [
            """Blahblah...
{BAD_CALENDAR_HINT: The Land of Mana-Storms and Spiders. 2021-08-11 0010}
MoreBlahblah!""",
            """Blahblah...
{CALEND@R_HINT: The Land of Mana-Storms and Spiders. 2021-08-11 0010}
MoreBlahblah!""",
            """Blahblah...
{CALENDAR_HINT: BAD}
MoreBlahblah!""",
            """Blahblah...
{CALENDAR_HINT: TWO HINTS - BAD FIRST!!!}
{CALENDAR_HINT: The Land of Mana-Storms and Spiders. 2021-08-11 0010}
MoreBlahblah!""",
        ]

        fail = False
        for str in parse_strings:
            try:
                metaplot, name_of_run, year, month, day, hours, minutes, timezone = Job.parse_selftext(str)
                fail = True
            except Exception:
                continue

            # Failure check
            if fail:
                self.fail("Expected exception not thrown for selftext" + str)

    @unittest.skipUnless(TEST_PARSING, "don't bother with parsing")
    def test_job_creation(self):
        # Test job syntactically correct (though incorrect - month is invalid) with a hint
        job = Job('The Prince of the West. 01-22-2022 @ 1800 UTC',
                  selftext="{CALENDAR_HINT: The Prince of the West. 22-01-2022 @ 1800 UTC}")
        self.assertEqual([job.year, job.month, job.day, job.hour, job.minute, int(job.get_start_datetime().timestamp())],
                         [2022, 1, 22, 18, 0, 1642874400])

        # Test job with timezone offset (canonical/long version)
        job = Job('The Prince of the West. 22-01-2022 @ 1800 UTC-6')
        self.assertEqual([job.year, job.month, job.day, job.hour, job.minute, int(job.get_start_datetime().timestamp())],
                         [2022, 1, 22, 18, 0, 1642896000])

        job = Job('The Prince of the West. 22-01-2022 @ 1800 UTC+0600')
        self.assertEqual([job.year, job.month, job.day, job.hour, job.minute, int(job.get_start_datetime().timestamp())],
                         [2022, 1, 22, 18, 0, 1642852800])

        job = Job('The Prince of the West. 22-01-2022 @ 1800 UTC-0600')
        self.assertEqual([job.year, job.month, job.day, job.hour, job.minute, int(job.get_start_datetime().timestamp())],
                         [2022, 1, 22, 18, 0, 1642896000])

        job = Job('The Prince of the West. 22-01-2022 @ 1800 UTC-06:00')
        self.assertEqual([job.year, job.month, job.day, job.hour, job.minute, int(job.get_start_datetime().timestamp())],
                         [2022, 1, 22, 18, 0, 1642896000])

        job = Job('The Prince of the West. 22-01-2022 @ 1800 UTC-06:30')
        self.assertEqual([job.year, job.month, job.day, job.hour, job.minute, int(job.get_start_datetime().timestamp())],
                         [2022, 1, 22, 18, 0, 1642897800])

        # Test job syntactically correct without hint
        job = Job('The Prince of the West. 01-22-2022 @ 1800 UTC')
        self.assertNotEqual([job.year, job.month, job.day], [2022, 1, 22])

        # Test job syntactically incorrect with a hint
        job = Job('CRAPCRAPCRAP', selftext="{CALENDAR_HINT: The Prince of the West. 22-01-2022 @ 1800 UTC}")
        self.assertEqual([job.year, job.month, job.day], [2022, 1, 22])

    # TODO - refactor - we're relying on test order to populate a class variable.
    @unittest.skipUnless(TEST_GOOGLE, "don't test Google")
    def test_authenticate(self):
        credentials = self.client.credentials('na','credentials.json')
        self.assertIsNotNone(credentials)
        self.service = self.client.authenticate(credentials)
        self.assertIsNotNone(self.service)

    @unittest.skipUnless(TEST_GOOGLE, "don't test Google")
    def test_crud_event(self):
        job = Job('[Metaplot, if any] Name of Run. 2021-04-01. 1234 UTC', post_id=666, permalink="/test",
                  author='fredbear')

        # create event from job
        job.flair = 'Job Open'
        self.client.create_event(job)

        # find it again
        event = self.client.find_event(job.post_id)
        self.assertIsNotNone(event)

        # Do not update flair - detect no change.
        response = self.client.update_event(event, job)
        self.assertIsNone(response)

        # Update job status
        job.flair = 'Job Closed'
        response = self.client.update_event(event, job)
        self.assertIsNotNone(response)

        # delete it
        self.client.delete_event(job.post_id)

        # find it again
        response = self.client.find_event(job.post_id)
        self.assertIsNone(response)

    @unittest.skipUnless(TEST_GOOGLE, "don't test Google")
    def test_find_future(self):
        events = self.client.find_future_events(datetime.datetime.utcnow())
        self.assertIsNotNone(events)


if __name__ == '__main__':
    unittest.main()
