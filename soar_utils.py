#!/usr/bin/env python3

from imp import load_module
from itertools import product
from os import environ as env, fsync
from os.path import exists, join
from subprocess import call, check_output, CalledProcessError, STDOUT
import inspect
import re
import sys

# dynamically find the Soar trunk
module_path = [p + "/Python_sml_ClientInterface.py" for p in sys.path if exists(join(p, "Python_sml_ClientInterface.py")) and "trunk" in p][0]
with open(module_path) as fd:
    module = load_module("Python_sml_ClientInterface", fd, module_path, ('.py', 'U', 1))
import Python_sml_ClientInterface as sml
from state2dot import state2dot

# SML wrappers

class Agent:
    class Identifier:
        def __init__(self, agent, identifier):
            self.agent = agent
            self.identifier = identifier
        def children(self):
            for index in range(self.identifier.GetNumberChildren()):
                yield self.agent.get_wme(self.identifier.GetChild(index))
        def __eq__(self, other):
            return isinstance(other, Agent.Identifier) and hash(self) == hash(other)
        def __hash__(self):
            return self.identifier.GetTimeTag()
    class WME:
        def __init__(self, agent, wme):
            self.agent = agent
            self.wme = wme
            self.value_type = self.wme.GetValueType()
        def get_identifier(self):
            return self.agent.get_identifier(self.wme.GetIdentifier())
        def get_attribute(self):
            return str(self.wme.GetAttribute())
        def get_value(self):
            if self.value_type == "int":
                return int(self.wme.ConvertToIntElement().GetValue())
            elif self.value_type == "float":
                return float(self.wme.ConvertToFloatElement().GetValue())
            elif self.value_type == "string":
                return str(self.wme.ConvertToStringElement().GetValue())
            else:
                return self.agent.get_identifier(self.wme.ConvertToIdentifier())
    def __init__(self, agent):
        self.agent = agent
        self.identifiers = {}
    def get_name(self):
        return str(self.agent.GetAgentName())
    def get_identifier(self, identifier):
        if identifier.GetTimeTag() not in self.identifiers:
            self.identifiers[identifier.GetTimeTag()] = Agent.Identifier(self, identifier)
        return self.identifiers[identifier.GetTimeTag()]
    def get_wme(self, wme):
        return Agent.WME(self, wme)
    def get_input_link(self):
        return self.get_identifier(self.agent.GetInputLink())
    def get_output_link(self):
        # this can be None if the agent has not put anything on the output link ever
        ol = self.agent.GetOutputLink()
        if ol:
            return self.get_identifier(ol)
        else:
            return None
    def create_wme(self, identifier, attribute, value):
        assert isinstance(identifier, Agent.Identifier)
        assert isinstance(attribute, str)
        if isinstance(value, int):
            return self.get_wme(self.agent.CreateIntWME(identifier.identifier, attribute, value))
        elif isinstance(value, float):
            return self.get_wme(self.agent.CreateFloatWME(identifier.identifier, attribute, value))
        elif isinstance(value, str):
            return self.get_wme(self.agent.CreateStringWME(identifier.identifier, attribute, value))
        elif isinstance(value, Agent.Identifier):
            return self.get_wme(self.agent.CreateIdWME(identifier.identifier, attribute, value))
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
        return self.kernel.DestroyAgent(agent)
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
            cmd = command.strip().split()[0]
            print(agent.execute_command_line(command).strip())
        command = input("soar> ")

def parameterize_commands(param_map, commands):
    return [cmd.format(**param_map) for cmd in commands]

def run_parameterized_commands(agent, param_map, commands):
    for cmd in parameterize_commands(param_map, commands):
        result = agent.ExecuteCommandLine(cmd)

def param_permutations(params):
    keys = sorted(params.keys())
    for values in product(*(params[key] for key in keys)):
        yield dict(zip(keys, values))

# environment template and example

class SoarEnvironment:
    def __init__(self, agent):
        self.agent = agent
        self.wmes = {}
        self.prev_state = None
        self.agent.register_for_run_event(sml.smlEVENT_AFTER_OUTPUT_PHASE, SoarEnvironment.update, self)
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
    def add_wme(self, parent, attr, child):
        if parent not in self.wmes:
            self.wmes[parent] = {}
        if attr not in self.wmes[parent]:
            self.wmes[parent][attr] = {}
        self.wmes[parent][attr][child] = self.agent.create_wme(parent, attr, child)
        return self.wmes[parent][attr][child]
    def parse_output_commands(self):
        commands = {}
        wmes = {}
        output_link = self.agent.get_output_link()
        if output_link is not None:
            for command in output_link.children():
                command_name = command.get_attribute()
                commands[command_name] = {}
                wmes[command_name] = command
                for parameter in command.get_value().children():
                    commands[command_name][parameter.get_attribute()] = parameter.get_value()
        return commands, wmes
    @staticmethod
    def update(mid, user_data, agent, message):
        user_data.update_io(mid, user_data, Agent(agent), message)
        agent.Commit()

class Ticker(SoarEnvironment):
    def __init__(self, agent):
        super().__init__(agent)
        self.time = 0
    def update_io(self, mid, user_data, agent, message):
        commands, wmes = self.parse_output_commands()
        if "print" in commands and "message" in commands["print"]:
            print(commands["print"]["message"])
        self.parse_output_commands()
        self.del_wme(agent.get_input_link(), "time", self.time)
        self.time += 1
        self.add_wme(agent.get_input_link(), "time", self.time)

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
    result = re.sub(".*\((.*) msec/decision.*", r"\1", agent.ExecuteCommandLine("stats"), flags=re.DOTALL)
    return ("avg_dc_msec", result)

def max_decision_time(param_map, domain, agent):
    result = re.sub(".*  Time \(sec\) *([0-9.]*).*", r"\1", agent.ExecuteCommandLine("stats -M"), flags=re.DOTALL)
    return ("max_dc_msec", float(result) * 1000)

def kernel_cpu_time(param_map, domain, agent):
    result = re.sub(".*Kernel CPU Time: *([0-9.]*).*", r"\1", agent.ExecuteCommandLine("stats"), flags=re.DOTALL)
    return ("kernel_cpu_msec", float(result) * 1000)

# soar code management

def make_branch(branch):
    try:
        stdout = check_output(("make-branch", branch), stderr=STDOUT)
        return True
    except CalledProcessError as cpe:
        return False

if __name__ == "__main__":
    agent = create_kernel_in_current_thread().create_agent("text")
    print(agent.execute_command_line("sp {print (state <s> ^superstate nil ^io <io>) (<io> ^output-link <ol> ^input-link.time <time>) --> (<ol> ^print.message <time>)}"))
    print(agent.execute_command_line("sp {halt (state <s> ^io.input-link <il>) (<il> ^time <t1> ^time {<t2> <> <t1>}) --> (write (crlf) |FAIL| (crlf)) (halt)}"))
    environment = Ticker(agent)
    cli(agent)
