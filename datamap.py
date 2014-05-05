#!/usr/bin/env python3

from pegparse import create_parser

class Symbol:
    UID = 0
    UNKNOWN_TYPE = "unknown"
    IDENTIFIER_TYPE = "identifier"
    STRING_TYPE = "string"
    NUMBER_TYPE = "number"
    def __init__(self):
        self.uid = Symbol.UID
        self.symbol_type = Symbol.UNKNOWN_TYPE
        self.values = set()
        self.name = self.uid
        Symbol.UID += 1
    def __str__(self):
        return "{} [label=\"{} ({})<br>{}<br>{}\"]".format(self.uid, self.name, self.uid, self.symbol_type, ",".join(self.values))

class WME:
    def __init__(self, identifier, attribute, value):
        self.identifier = identifier
        self.attribute = attribute
        self.value = value
    def __str__(self):
        result = []
        result.append(self.identifier.__str__())
        result.append(self.attribute.__str__())
        result.append(self.value.__str__())
        result.append("{} -> {} [label=\"{}\"]".format(self.identifier.uid, self.value.uid, self.attribute.uid))
        return "\n".join(result)

def merge_symbols(symbols):
    sym = Symbol()
    types = set(symbol.symbol_type for symbol in symbols)
    if len(types) == 1:
        sym.symbol_type = types.pop()
    for symbol in symbols:
        sym.values.update(symbol.values)
    return sym

def parse_condition(ast):
    result = []
    print(ast.term)
    if ast.term == "ConditionForOneIdentifier":
        return parse_condition(ast.first_descendant("VariableTest"))
    elif ast.term in ("VariableTest", "StructuredValueTest"):
        ast.pretty_print()
        identifier = Symbol()
        identifier.symbol_type = Symbol.IDENTIFIER_TYPE
        if ast.descendants("Variable"):
            identifier.name = ast.first_descendant("Variable").match
        descendantry = ast.descendants("AttributeValueTest")
        # FIXME need an outer loop for attribute*-value*'s
        for descendant in descendantry[:-1]:
            attribute = parse_symbol(descendant)
            value = Symbol()
            value.symbol_type = Symbol.IDENTIFIER_TYPE
            result.append(WME(identifier, attribute, value))
            identifier = value
        attribute = parse_symbol(descendantry[-1].firstDescendant("AttributeTest/Test/*"))
        for descendant in ast.descendants("ValueTest/*"):
            if ast.term == "PreferenceTest":
                value = parse_symbol(descendant.first_descendant("Test/*"))
                result.append(WME(identifier, attribute, value))
            else:
                result.extend(parse_condition(descendant))
    return result

def parse_symbol(ast):
    result = Symbol()
    if ast.term == "ConjunctiveTest":
        result = merge_symbols([parse_symbol(child) for child in ast.descendants("SimpleTest/*")])
    elif ast.term == "DisjunctiveTest":
        result.values.update(constant.match for constant in ast.descendants("Constant"))
    elif ast.term == "RelationalTest":
        result.symbol_type = "number"
    elif ast.term == "SingleTest":
        if ast.descendants("Constant"):
            if ast.descendants("Constant/SymbolicConstant"):
                result.symbol_type = Symbol.STRING_TYPE
            else:
                result.symbol_type = Symbol.NUMBER_TYPE
            result.values.update(ast.match)
    return result

if __name__ == "__main__":
    with open("soar-grammar", "r") as fd:
        grammar = fd.read()
    parser = create_parser(grammar)
    ast = parser.parse("(state <s> ^superstate nil)", "ConditionForOneIdentifier", complete=True)
    if ast:
        result = parse_condition(ast)
        print(result)
    else:
        print("parse failed")
