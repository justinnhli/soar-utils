#!/usr/bin/env python3

from abc import abstractmethod
from ast import literal_eval
from copy import deepcopy
from imp import load_module
from itertools import product
from os.path import exists, join
import inspect
import re
import sys

# dynamically find the Soar trunk
module_path = [p + "/Python_sml_ClientInterface.py" for p in sys.path if exists(join(p, "Python_sml_ClientInterface.py")) and "trunk" in p][0]
with open(module_path) as fd:
    module = load_module("Python_sml_ClientInterface", fd, module_path, ('.py', 'U', 1))
import Python_sml_ClientInterface as sml

# SML wrappers

class Agent:
    class Identifier:
        def __init__(self, agent, wme):
            assert isinstance(wme, sml.Identifier)
            self.agent = agent
            self.wme = wme
        def __eq__(self, other):
            return isinstance(other, Agent.Identifier) and hash(self) == hash(other)
        def __hash__(self):
            return self.time_tag
        @property
        def time_tag(self):
            return self.wme.GetTimeTag()
        def children(self):
            for index in range(self.wme.GetNumberChildren()):
                yield self.agent._get_wme(self.wme.GetChild(index))
        def add_child(self, attribute, value):
            self.agent.create_wme(self, attribute, value)
    class WME:
        def __init__(self, agent, wme):
            assert isinstance(wme, sml.WMElement)
            self.agent = agent
            self.wme = wme
        @property
        def identifier(self):
            return self.agent._get_identifier(self.wme.ConvertToIdentifier())
        @property
        def attribute(self):
            return str(self.wme.GetAttribute())
        @property
        def value_type(self):
            value_type = self.wme.GetValueType()
            if value_type == "int":
                return int
            elif value_type == "float":
                return float
            elif value_type == "string":
                value = self.wme.ConvertToStringElement().GetValue()
                if value in ("true", "false"):
                    return bool
                else:
                    return str
            else:
                return Agent.Identifier
        @property
        def value(self):
            if self.value_type == bool:
                return False if str(self.wme.ConvertToStringElement().GetValue()) == "false" else True
            elif self.value_type == int:
                return int(self.wme.ConvertToIntElement().GetValue())
            elif self.value_type == float:
                return float(self.wme.ConvertToFloatElement().GetValue())
            elif self.value_type == str:
                return str(self.wme.ConvertToStringElement().GetValue())
            else:
                return self.agent._get_identifier(self.wme.ConvertToIdentifier())
    def __init__(self, agent):
        self.agent = agent
        self.identifiers = {}
    @property
    def name(self):
        return str(self.agent.GetAgentName())
    @property
    def input_link(self):
        return self._get_identifier(self.agent.GetInputLink())
    @property
    def output_link(self):
        # this can be None if the agent has not put anything on the output link ever
        ol = self.agent.GetOutputLink()
        if ol:
            return self._get_identifier(ol)
        else:
            return None
    def _get_identifier(self, identifier):
        assert isinstance(identifier, sml.Identifier)
        if identifier.GetTimeTag() not in self.identifiers:
            self.identifiers[identifier.GetTimeTag()] = Agent.Identifier(self, identifier)
        return self.identifiers[identifier.GetTimeTag()]
    def _get_wme(self, wme):
        assert isinstance(wme, sml.WMElement)
        return Agent.WME(self, wme)
    def create_wme(self, identifier, attribute, value):
        assert isinstance(identifier, Agent.Identifier)
        assert isinstance(attribute, str)
        if isinstance(value, bool):
            return self._get_wme(self.agent.CreateStringWME(identifier.wme, attribute, ("true" if value else "false")))
        if isinstance(value, int):
            return self._get_wme(self.agent.CreateIntWME(identifier.wme, attribute, value))
        elif isinstance(value, float):
            return self._get_wme(self.agent.CreateFloatWME(identifier.wme, attribute, value))
        elif isinstance(value, str):
            return self._get_wme(self.agent.CreateStringWME(identifier.wme, attribute, value))
        elif isinstance(value, Agent.Identifier):
            return self._get_wme(self.agent.CreateSharedIdWME(identifier.wme, attribute, value))
        elif value is None:
            return self._get_wme(self.agent.CreateIdWME(identifier.wme, attribute))
        else:
            raise TypeError()
    def destroy_wme(self, wme):
        assert isinstance(wme, Agent.WME)
        return bool(self.agent.DestroyWME(wme.wme))
    def execute_command_line(self, command):
        return str(self.agent.ExecuteCommandLine(command))
    def register_for_run_event(self, event, function, user_data):
        return int(self.agent.RegisterForRunEvent(event, function, user_data))
    def unregister_for_run_event(self, event_id):
        return bool(self.agent.UnregisterForRunEvent(event_id))
    def register_for_print_event(self, event, function, user_data):
        return int(self.agent.RegisterForPrintEvent(event, function, user_data))
    def unregister_for_print_event(self, event_id):
        return bool(self.agent.UnregisterForPrintEvent(event_id))

class Kernel:
    def __init__(self, kernel):
        self.kernel = kernel
    def create_agent(self, name):
        agent = self.kernel.CreateAgent(name)
        if agent is None:
            raise RuntimeError("Error creating agent: " + self.kernel.GetLastErrorDescription())
        return Agent(agent)
    def destroy_agent(self, agent):
        assert isinstance(agent, Agent)
        return self.kernel.DestroyAgent(agent.agent)
    def shutdown(self):
        return self.kernel.Shutdown()

def create_kernel_in_current_thread():
    kernel = sml.Kernel.CreateKernelInCurrentThread()
    if kernel is None or kernel.HadError():
        raise RuntimeError("Error creating kernel: " + kernel.GetLastErrorDescription())
    return Kernel(kernel)

# mid-level framework

def cli(agent):
    agent.register_for_print_event(sml.smlEVENT_PRINT, callback_print_message, None)
    command = input("soar> ")
    while command not in ("exit", "quit"):
        if command:
            print(agent.execute_command_line(command).strip())
        command = input("soar> ")

def str_to_parameters(s):
    parameters = {}
    for pair in s.split():
        k, v = pair.split("=")
        try:
            v = literal_eval(v)
        except SyntaxError:
            pass
        parameters[k] = v
    return parameters

def parameterize_commands(param_map, commands):
    return [cmd.format(**param_map) for cmd in commands]

def run_parameterized_commands(agent, param_map, commands):
    for cmd in parameterize_commands(param_map, commands):
        agent.ExecuteCommandLine(cmd)

def parameter_permutations(params):
    keys = sorted(params.keys())
    for values in product(*(params[key] for key in keys)):
        original = dict(zip(keys, values))
        modified = {}
        changed = True
        while changed:
            changed = False
            for k, v in original.items():
                if isinstance(v, str):
                    replaced_v = v.format(**original)
                    if replaced_v != v:
                        changed = True
                    modified[k] = replaced_v
                else:
                    modified[k] = v
            original, modified = modified, {}
        yield original

# environment template and example

class SoarEnvironment:
    class Command:
        def __init__(self, wme):
            assert isinstance(wme, Agent.WME)
            self.wme = wme
            self.name = self.wme.attribute
            self.parameters = {}
            for parameter in self.wme.value.children():
                self.parameters[parameter.attribute] = parameter.value
        def add_status(self, status):
            self.wme.value.add_child("status", status)
    def __init__(self, agent):
        self.agent = agent
        self.wmes = {}
        self.processed_commands = set()
        self.io_initialized = False
        self.agent.register_for_run_event(sml.smlEVENT_AFTER_OUTPUT_PHASE, SoarEnvironment.update, self)
    @abstractmethod
    def initialize_io(self):
        raise NotImplementedError()
    @abstractmethod
    def update_io(self, mid, user_data, agent, message):
        raise NotImplementedError()
    def del_wme(self, parent, attr, child):
        if (parent not in self.wmes) or (attr not in self.wmes[parent]) or (child not in self.wmes[parent][attr]):
            return False
        self.agent.destroy_wme(self.wmes[parent][attr][child])
        del self.wmes[parent][attr][child]
        if len(self.wmes[parent][attr]) == 0:
            del self.wmes[parent][attr]
        if len(self.wmes[parent]) == 0:
            del self.wmes[parent]
        return True
    def add_wme(self, parent, attr, child=None):
        if parent not in self.wmes:
            self.wmes[parent] = {}
        if attr not in self.wmes[parent]:
            self.wmes[parent][attr] = {}
        new_wme = None
        if child is None:
            self.wmes[parent][attr][child] = set()
            new_wme = self.agent.create_wme(parent, attr, child)
            self.wmes[parent][attr][child].add(new_wme)
        else:
            new_wme = self.agent.create_wme(parent, attr, child)
            self.wmes[parent][attr][child] = new_wme
        return new_wme
    def parse_output_commands(self):
        commands = set()
        output_link = self.agent.output_link
        if output_link is not None:
            for command_wme in output_link.children():
                if command_wme.identifier.time_tag not in self.processed_commands:
                    commands.add(SoarEnvironment.Command(command_wme))
                    self.processed_commands.add(command_wme.identifier.time_tag)
        return commands
    @staticmethod
    def update(mid, user_data, agent, message):
        if not user_data.io_initialized:
            user_data.initialize_io()
            user_data.io_initialized = True
        user_data.update_io(mid, user_data, Agent(agent), message)
        agent.Commit()

class Ticker(SoarEnvironment):
    def __init__(self, agent):
        super().__init__(agent)
        self.time = 0
    def update_io(self, mid, user_data, agent, message):
        commands = self.parse_output_commands()
        for command in commands:
            if command.name == "print" and "message" in command.params:
                print(command.params["message"])
                command.add_status("complete")
            else:
                command.add_status("error")
        self.del_wme(agent.input_link, "time", self.time)
        self.time += 1
        self.add_wme(agent.input_link, "time", self.time)

class ParameterizedSoarEnvironment(SoarEnvironment):
    def __init__(self, parameters, agent):
        super().__init__(agent)
        self.parameters = parameters

# experiment template and example

class SoarExperiment:
    def __init__(self, name, environment_class, parameter_space, commands, reporters):
        self.name = name
        self.environment_class = environment_class
        self.parameter_space = parameter_space
        self.parameter_space["experiment_name"] = (self.name,)
        self.commands = commands
        self.reporters = reporters
        self.prerun_procedures = set()
    def register_prerun_procedure(self, f):
        self.prerun_procedures.add(f)
    def print_independent_variables(self):
        for k, v in sorted(self.parameter_space.items()):
            if len(v) > 1:
                print("# {}: {}".format(k, v))
    def run(self, with_cli=False, fixed_parameters=None):
        parameter_space = deepcopy(self.parameter_space)
        if fixed_parameters:
            for k, v in fixed_parameters.items():
                parameter_space[k] = (v,)
        for parameters in parameter_permutations(parameter_space):
            report = {}
            report.update(parameters)
            kernel = create_kernel_in_current_thread()
            agent = kernel.create_agent("test")
            environment = self.environment_class(parameters, agent)
            for f in self.prerun_procedures:
                f(environment, parameters, agent)
            if with_cli:
                for command in parameterize_commands(parameters, self.commands):
                    print("soar> " + command.strip())
                    print(agent.execute_command_line(command).strip())
                agent.execute_command_line("watch 1")
                cli(agent)
            else:
                for command in parameterize_commands(parameters, self.commands):
                    agent.execute_command_line(command)
                agent.execute_command_line("run")
            for name, reporter in self.reporters.items():
                report[name] = reporter(environment, parameters, agent)
            kernel.destroy_agent(agent)
            kernel.shutdown()
            del kernel
            print(" ".join("{}={}".format(k, v) for k, v in sorted(report.items())))

# callback functions

def callback_print_message(mid, user_data, agent, message):
    print(message.strip())

def print_report_row(mid, user_data, agent, *args):
    condition = user_data["condition"]
    param_map = user_data["param_map"]
    domain = user_data["domain"]
    reporters = user_data["reporters"]
    if condition(param_map, domain, agent):
        pairs = []
        pairs.extend("=".join([k, str(v)]) for k, v in param_map.items())
        pairs.extend("{}={}".format(*reporter(param_map, domain, agent)) for reporter in reporters)
        print(" ".join(pairs))

def report_data_wrapper(param_map, domain, reporters, condition=None):
    if condition is None:
        condition = (lambda param_map, domain, agent: True)
    return {
        "condition": condition,
        "param_map": param_map,
        "domain": domain,
        "reporters": reporters,
    }

# common reporters

def soar_path(param_map, domain, agent):
    return ("computed_branch", inspect.getfile(sml))

def num_decisions(param_map, domain, agent):
    result = re.sub("^([^ ]*) decisions.*", r"\1", agent.ExecuteCommandLine("stats"), flags=re.DOTALL)
    return ("num_decisions", result)

def avg_decision_time(param_map, domain, agent):
    result = re.sub(r".*\((.*) msec/decision.*", r"\1", agent.ExecuteCommandLine("stats"), flags=re.DOTALL)
    return ("avg_dc_msec", result)

def max_decision_time(param_map, domain, agent):
    result = re.sub(r".*  Time \(sec\) *([0-9.]*).*", r"\1", agent.ExecuteCommandLine("stats -M"), flags=re.DOTALL)
    return ("max_dc_msec", float(result) * 1000)

def kernel_cpu_time(param_map, domain, agent):
    result = re.sub(".*Kernel CPU Time: *([0-9.]*).*", r"\1", agent.ExecuteCommandLine("stats"), flags=re.DOTALL)
    return ("kernel_cpu_msec", float(result) * 1000)

if __name__ == "__main__":
    agent = create_kernel_in_current_thread().create_agent("text")
    print(agent.execute_command_line("""
        sp {propose*init-agent
            (state <s> ^superstate nil
                      -^name)
        -->
            (<s> ^operator.name init-agent)
        }
        sp {apply*init-agent
            (state <s> ^operator.name init-agent)
        -->
            (<s> ^name ticker)
        }
        sp {ticker*propose*print
            (state <s> ^name ticker
                       ^io.input-link.time <time>)
        -->
            (<s> ^operator.name print)
        }
        sp {ticker*apply*print
            (state <s> ^name ticker
                       ^operator.name print
                       ^io <io>)
            (<io> ^input-link.time <time>
                  ^output-link <ol>)
        -->
            (<ol> ^print.message <time>)
        }
        sp {ticker*apply*all*remove-completed
            (state <s> ^operator.name
                       ^io.output-link <ol>)
            (<ol> ^<command> <cmd>)
            (<cmd> ^status complete)
        -->
            (<ol> ^<command> <cmd> -)
        }
        sp {ticker*fail
            (state <s> ^io.input-link <il>)
            (<il> ^time <t1>
                  ^time {<t2> <> <t1>})
        -->
            (write (crlf) |FAIL| (crlf))
            (halt)
        }
    """))
    environment = Ticker(agent)
    cli(agent)
