#!/usr/bin/env python3

from pegparse import create_parser
import sys

def simple_test_indent(simple_test_ast):
    tokens = []
    if test_ast.descendants("DisjunctiveTest"):
        tokens.append("<< ")
        tokens.append(" ".join(ast.match for ast in test_ast.descendants("DisjunctiveTest/Constant")))
        tokens.append(" >>")
    else:
        if test_ast.descendants("RelationalTest/Relation"):
            tokens.append(test_ast.first_descendant("RelationalTest/Relation").match)
            tokens.append(" ")
        tokens.append(test_ast.first_descendant("RelationalTest/SingleTest").match)
    return tokens

def test_indent(test_ast):
    tokens = []
    if test_ast.descendants("ConjunctiveTest"):
        tokens.append("{")
        if test_ast.descendants("ConjunctiveTest/Variable"):
            tokens.append(test_ast.first_descendant("ConjunctiveTest/Variable").match)
        for simple_test_ast in test_ast.descendants("ConjunctiveTest/SimpleTest"):
            tokens.append(" ")
            tokens.extend(simple_test_indent(simple_test_ast))
        tokens.append("}")
    else:
        tokens = simple_test_indent(test_ast.first_descendant("SimpleTest"))
    return tokens

def attribute_value_indent(attr_val_ast, indent):
    if attr_val_ast.descendants("NegationSpecifier"):
        tokens = [indent * " ", "-"]
    else:
        tokens = [(indent + 1) * " ", ]
    tokens.append("^")
    tokens.append(".".join("".join(test_indent(test_ast)) for test_ast in attr_val_ast.descendants("AttributeTest/Test")))
    if attr_val_ast.descendants("ValueTest"):
        for val_test_ast in attr_val_ast.descendants("ValueTest"):
            tokens.append(" ")
            if val_test_ast.descendants("PreferenceTest"):
                tokens.extend(test_indent(val_test_ast.first_descendant("PreferenceTest/Test")))
                if val_test_ast.descendants("PreferenceTest/AcceptableSpecifier"):
                    tokens.extend(" +")
            else:
                tokens.append("(")
                if val_test_ast.descendants("StructuredValueTest/Variable"):
                    tokens.append(val_test_ast.first_descendant("StructuredValueTest/Variable").match)
                    tokens.append(" ")
                child_indent = 0 # FIXME
                for child in val_test_ast.descendants("StructureValueTest/AttributeValueTest"):
                    tokens.append(" ".join("".join(attribute_value_indent(child, child_indent))))
                    tokens.append("\n")
                    tokens.append(child_indent * " ")
                tokens.append(")")
    return tokens

def condition_indent(condition_ast, indent):
    if condition_ast.descendants("NegationSpecifier"):
        tokens = [indent * " ", "-"]
    else:
        tokens = [(indent + 1) * " ", ]
    tokens.append("(")
    elif condition_ast.descendants("PositiveCondition/ConditionForOneIdentifier"):
        pass
    elif:
        pass
    if condition.descendants("StateSpecifier"):
        tokens.append("state ")
    tokens.append(condition.first_descendant("VariableTest/Variable").match)
    indent = len("".join(tokens))
    for attr_val_ast in condition.descendants("VariableTest/AttributeValueTest"):
        tokens.extend(attribute_value_indent(attr_val_ast, indent + 1)
        tokens.append("\n")
        tokens.append(indent * " ")
    tokens.append(")")

def soar_indent(text):
    text = text.strip()
    with open("/Users/justinnhli/projects/soar_exp/soar-grammar", "r") as fd:
        parser = create_parser(fd.read())
    soar_ast = parser.parse(text, "SoarFile", complete=True)
    if not soar_ast:
        return None
    last_term = ""
    for ast in soar_ast.descendants("*"):
        if ast.term == "OptWhitespace":
            if ast.descendants("Space/Comment"):
                if last_term != "Comment":
                    print("")
                print("\n".join(ast.match.strip() for ast in ast.descendants("Space/Comment")))
                last_term = "Comment"
        elif ast.descendants("Tcl"):
            if last_term != "Tcl":
                print("")
            print(ast.first_descendant("Tcl").match.strip())
            last_term = "Tcl"
        else:
            production_ast = ast.first_descendant("SoarProduction")
            print("")
            print("sp {{{}".format(production_ast.first_descendant("ProductionName").match))
            if production_ast.descendants("Documentation"):
                print("   {}".format(production_ast.first_descendant("Documentation")))
            if production_ast.descendants("ProductionType"):
                print("   {}".format(" ".join(ast.match for ast in production_ast.descendants("ProductionType"))))
            conditions = [ast.first_descendant("ConditionSide/FirstCondition"),]
            conditions.extend(ast.descendants("ConditionSide/Condition"))
            for condition_ast in conditions:
                if condition_ast.term == "FirstCondition":
                    tokens = condition_indent(condition_ast, 2)
                elif condition_ast.descendants("PositiveCondition/ConditionForOneIdentifier"):
                    tokens = condition_indent(condition_ast.first_descendant("PositiveCondition/ConditionForOneIdentifier"), 2)
                print("".join(tokens))
            print("-->")
            print("}")
            last_term = "SoarProduction"

if __name__ == "__main__":
    with open(sys.argv[1], "r") as fd:
        soar_indent(fd.read())
