#! /usr/bin/env python

import sys
import re

import pybindgen
from pybindgen.typehandlers import base as typehandlers
from pybindgen import (ReturnValue, Parameter, Module, Function, FileCodeSink)
from pybindgen import (CppMethod, CppConstructor, CppClass, Enum)
from pybindgen.gccxmlparser import ModuleParser
from pybindgen.function import CustomFunctionWrapper
from pybindgen.cppmethod import CustomCppMethodWrapper



class PointerHolderTransformation(typehandlers.TypeTransformation):
    def __init__(self):
        self.rx = re.compile(r'(?:::)?PointerHolder<(\w+)>')

    def get_untransformed_name(self, name):
        m = self.rx.match(name)
        if m is None:
            return None
        else:
            return m.group(1)+'*'

    def create_type_handler(self, type_handler, *args, **kwargs):
        if issubclass(type_handler, Parameter):
            kwargs['transfer_ownership'] = False
        elif issubclass(type_handler, ReturnValue):
            kwargs['caller_owns_return'] = True
        else:
            raise AssertionError
        handler = type_handler(*args, **kwargs)
        handler.set_tranformation(self, self.get_untransformed_name(args[0]))
        return handler

    def untransform(self, type_handler, declarations, code_block, expression):
        return '(%s).thePointer' % (expression,)

    def transform(self, type_handler, declarations, code_block, expression):
        assert type_handler.untransformed_ctype[-1] == '*'
        var = declarations.declare_variable(
            'PointerHolder<%s>' % type_handler.untransformed_ctype[:-1], 'tmp')
        return '(%s.thePointer = (%s), %s)' % (var, expression, var)

transf = PointerHolderTransformation()
typehandlers.return_type_matcher.register_transformation(transf)
typehandlers.param_type_matcher.register_transformation(transf)
del transf



def customize_module(module):
    wrapper_body = '''
static PyObject *
_wrap_foofunction_that_takes_foo_from_string(PyObject * PYBINDGEN_UNUSED(dummy), PyObject *args,
                                             PyObject *kwargs, PyObject **return_exception)
{
    PyObject *py_retval;
    char *datum;
    const char *keywords[] = {"foo", NULL};

    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "s", (char **) keywords, &datum)) {
        {
            PyObject *exc_type, *traceback;
            PyErr_Fetch(&exc_type, return_exception, &traceback);
            Py_XDECREF(exc_type);
            Py_XDECREF(traceback);
        }
        return NULL;
    }
    function_that_takes_foo(Foo(datum));
    py_retval = Py_BuildValue("");
    return py_retval;
}
'''
    module.add_custom_function_wrapper('function_that_takes_foo',
                                       '_wrap_foofunction_that_takes_foo_from_string',
                                       wrapper_body)


    ## test a custom method wrapper
    Bar, = [cls for cls in module.classes if cls.name == 'Bar']
    wrapper_body = '''
static PyObject *
_wrap_PyBar_Hooray_lenx(PyBar *PYBINDGEN_UNUSED(dummy), PyObject *args, PyObject *kwargs,
                        PyObject **return_exception)
{
    PyObject *py_retval;
    int x;
    const char *keywords[] = {"x", NULL};

    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "i", (char **) keywords, &x)) {
        PyObject *exc_type, *traceback;
        PyErr_Fetch(&exc_type, return_exception, &traceback);
        Py_XDECREF(exc_type);
        Py_XDECREF(traceback);
        return NULL;
    }

    std::string retval;
    retval = Bar::Hooray();
    py_retval = Py_BuildValue("i", int(retval.size() + x));
    return py_retval;
}
'''
    Bar.add_method(CustomCppMethodWrapper("Hooray", "_wrap_PyBar_Hooray_lenx",
                                          wrapper_body,
                                          flags=["METH_VARARGS", "METH_KEYWORDS", "METH_STATIC"]))


    Foo, = [cls for cls in module.classes if cls.name == 'Foo']
    def Foo_instance_creation_function(dummy_cpp_class, code_block, lvalue,
                                       parameters, construct_type_name):
        code_block.write_code(
            "%s = new %s(%s);" % (lvalue, construct_type_name, parameters))
        code_block.write_code("%s->initialize();" % (lvalue,))
    Foo.set_instance_creation_function(Foo_instance_creation_function)

