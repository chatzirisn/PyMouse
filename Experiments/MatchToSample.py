from core.Experiment import *


@experiment.schema
class Condition(dj.Manual):
    class MatchToSample(dj.Part):
        definition = """
        # Match2Sample experiment conditions
        -> Condition
        ---
        trial_selection='staircase' : enum('fixed','random','staircase','biased') 
        max_reward=3000             : smallint
        min_reward=500              : smallint
        bias_window=5               : smallint
        staircase_window=20         : smallint
        stair_up=0.7                : float
        stair_down=0.55             : float
        noresponse_intertrial=1     : tinyint(1)
        incremental_punishment=1    : tinyint(1)
    
        difficulty                  : int   
        init_ready                  : int
        cue_ready                   : int
        delay_ready                 : int
        resp_ready                  : int
        intertrial_duration         : int
        cue_duration                : int
        delay_duration              : int
        response_duration           : int
        reward_duration             : int
        punish_duration             : int
        abort_duration              : int 
        """


class Experiment(State, ExperimentClass):
    cond_tables = ['MatchToSample']
    required_fields = ['difficulty']
    default_key = {'trial_selection'     : 'staircase',
                   'max_reward'            : 3000,
                   'min_reward'            : 500,
                   'bias_window'           : 5,
                   'staircase_window'      : 20,
                   'stair_up'              : 0.7,
                   'stair_down'            : 0.55,
                   'noresponse_intertrial' : True,
                   'incremental_punishment': True,

                   'init_ready'             : 0,
                   'cue_ready'              : 0,
                   'delay_ready'            : 0,
                   'resp_ready'             : 0,
                   'intertrial_duration'    : 1000,
                   'cue_duration'           : 1000,
                   'delay_duration'         : 0,
                   'response_duration'      : 5000,
                   'reward_duration'        : 2000,
                   'punish_duration'        : 1000,
                   'abort_duration'         : 0}

    def entry(self):  # updates stateMachine from Database entry - override for timing critical transitions
        self.logger.curr_state = self.name()
        self.start_time = self.logger.log('Trial.StateOnset', {'state': self.name()})
        self.resp_ready = False
        self.state_timer.start()


class Entry(Experiment):
    def entry(self):
        pass

    def next(self):
        return 'PreTrial'


class PreTrial(Experiment):
    def entry(self):
        self.prepare_trial()
        self.beh.prepare(self.curr_cond)
        self.stim.prepare(self.curr_cond, 'Cue')
        super().entry()

    def run(self):
        if not self.is_stopped() and self.beh.is_ready(self.curr_cond['init_ready'], self.start_time):
            self.resp_ready = True
        self.logger.ping()

    def next(self):
        if self.is_stopped():
            return 'Exit'
        elif self.beh.is_sleep_time():
            return 'Offtime'
        elif self.resp_ready:
            return 'Cue'
        else:
            return 'PreTrial'


class Cue(Experiment):
    def entry(self):
        self.stim.start()
        super().entry()

    def run(self):
        self.stim.present()
        self.logger.ping()
        self.response = self.beh.get_response(self.start_time)
        if self.beh.is_ready(self.curr_cond['cue_ready'], self.start_time):
            self.resp_ready = True

    def next(self):
        elapsed_time = self.state_timer.elapsed_time()
        if self.resp_ready and (self.curr_cond['cue_ready'] or elapsed_time > self.curr_cond['cue_duration']):
            return 'Delay'
        elif self.response:
            return 'Abort'
        elif elapsed_time > self.curr_cond['cue_duration']:
            return 'Abort'
        elif self.is_stopped():  # if wake up then update session
            return 'Exit'
        else:
            return 'Cue'

    def exit(self):
        self.stim.stop()


class Delay(Experiment):
    def entry(self):
        self.stim.prepare(self.curr_cond, 'Response')
        super().entry()

    def run(self):
        self.response = self.beh.get_response(self.start_time)
        if self.beh.is_ready(self.curr_cond['delay_ready'], self.start_time):
            self.resp_ready = True

    def next(self):
        if self.resp_ready and self.state_timer.elapsed_time() > self.curr_cond['delay_duration']: # this specifies the minimum amount of time we want to spend in the delay period contrary to the cue_duration FIX IT
            return 'Response'
        elif self.response:
            return 'Abort'
        elif self.is_stopped():
            return 'Exit'
        else:
            return 'Delay'


class Response(Experiment):
    def entry(self):
        self.stim.start()
        super().entry()

    def run(self):
        self.stim.present()  # Start Stimulus
        self.logger.ping()
        self.response = self.beh.get_response(self.start_time)
        if self.beh.is_ready(self.curr_cond['resp_ready'], self.start_time):
            self.resp_ready = True

    def next(self):
        if self.response and self.beh.is_correct() and self.resp_ready:  # correct response
            return 'Reward'
        elif not self.resp_ready and self.response:
            return 'Abort'
        elif self.response and not self.beh.is_correct():  # incorrect response
            return 'Punish'
        elif self.state_timer.elapsed_time() > self.curr_cond['response_duration']:      # timed out
            return 'Abort'
        elif self.is_stopped():
            return 'Exit'
        else:
            return 'Response'

    def exit(self):
        self.stim.stop()
        self.logger.ping()


class Abort(Experiment):
    def entry(self):
        super().entry()
        self.beh.update_history()
        self.logger.log('Trial.Aborted')

    def next(self):
        if self.state_timer.elapsed_time() >= self.curr_cond['abort_duration']:
            return 'InterTrial'
        elif self.is_stopped():
            return 'Exit'
        else:
            return 'Abort'


class Reward(Experiment):
    def entry(self):
        super().entry()
        self.stim.reward_stim()

    def run(self):
        self.rewarded = self.beh.reward()

    def next(self):
        if self.rewarded or self.state_timer.elapsed_time() >= self.curr_cond['reward_duration']:
            return 'InterTrial'
        elif self.is_stopped():
            return 'Exit'
        else:
            return 'Reward'


class Punish(Experiment):
    def entry(self):
        self.beh.punish()
        super().entry()
        self.punish_period = self.curr_cond['punish_duration']
        if self.params.get('incremental_punishment'):
            self.punish_period *= self.beh.get_false_history()

    def run(self):
        self.stim.punish_stim()

    def next(self):
        if self.state_timer.elapsed_time() >= self.punish_period:
            return 'InterTrial'
        elif self.is_stopped():
            return 'Exit'
        else:
            return 'Punish'


class InterTrial(Experiment):
    def entry(self):
        super().entry()

    def run(self):
        if self.beh.get_response(self.start_time) & self.params.get('noresponse_intertrial'):
            self.state_timer.start()

    def next(self):
        if self.is_stopped():
            return 'Exit'
        elif self.beh.is_sleep_time() and not self.beh.is_hydrated(self.params['min_reward']):
            return 'Hydrate'
        elif self.beh.is_sleep_time() or self.beh.is_hydrated():
            return 'Offtime'
        elif self.state_timer.elapsed_time() >= self.curr_cond['intertrial_duration']:
            return 'PreTrial'
        else:
            return 'InterTrial'

    def exit(self):
        self.stim.unshow()


class Hydrate(Experiment):
    def run(self):
        if self.beh.get_response():
            self.beh.reward()
            time.sleep(1)
        self.logger.ping()

    def next(self):
        if self.is_stopped():  # if wake up then update session
            return 'Exit'
        elif self.beh.is_hydrated(self.params['min_reward']) or not self.beh.is_sleep_time():
            return 'Offtime'
        else:
            return 'Hydrate'


class Offtime(Experiment):
    def entry(self):
        super().entry()
        self.stim.unshow([0, 0, 0])

    def run(self):
        if self.logger.setup_status not in ['sleeping', 'wakeup'] and self.beh.is_sleep_time():
            self.logger.update_setup_info({'status': 'sleeping'})
        self.logger.ping()
        time.sleep(1)

    def next(self):
        if self.is_stopped():  # if wake up then update session
            return 'Exit'
        elif self.logger.setup_status == 'wakeup' and not self.beh.is_sleep_time():
            return 'PreTrial'
        elif self.logger.setup_status == 'sleeping' and not self.beh.is_sleep_time():  # if wake up then update session
            return 'Exit'
        elif not self.beh.is_hydrated() and not self.beh.is_sleep_time():
            return 'Exit'
        else:
            return 'Offtime'

    def exit(self):
        if self.logger.setup_status in ['wakeup', 'sleeping']:
            self.logger.update_setup_info({'status': 'running'})


class Exit(Experiment):
    def run(self):
        self.beh.exit()
        self.stim.exit()
        self.logger.ping(0)
