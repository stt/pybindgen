
import sys
PY3 = (sys.version_info[0] >= 3)

if PY3:
    string_types = str,
else:
    string_types = basestring,

try:
    any = any
except NameError:
    def any(iterable):
        for element in iterable:
            if element:
                return True
        return False


from pybindgen.typehandlers.codesink import CodeSink
from pybindgen.typehandlers.base import TypeLookupError, TypeConfigurationError, CodeGenerationError, NotSupportedError, \
    Parameter, ReturnValue
try:
    from pybindgen.version import __version__
except ImportError:
    __version__ = [0, 0, 0, 0]

from pybindgen import settings
import warnings


def write_preamble(code_sink, min_python_version=None):
    """
    Write a preamble, containing includes, #define's and typedef's
    necessary to correctly compile the code with the given minimum python
    version.
    """
    if min_python_version is None:
        min_python_version = settings.min_python_version
    assert isinstance(code_sink, CodeSink)
    assert isinstance(min_python_version, tuple)

    if __debug__:
        ## Gracefully allow code migration
        if hasattr(code_sink, "have_written_preamble"):
            warnings.warn("Duplicate call to write_preamble detected.  "
                          "Note that there has been an API change in PyBindGen "
                          "and directly calling write_preamble should no longer be done "
                          "as it is done by PyBindGen itself.",
                          DeprecationWarning, stacklevel=2)
            return
        else:
            setattr(code_sink, "have_written_preamble", None)

    code_sink.writeln('''/* This file was generated by PyBindGen %s */
#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <stddef.h>
''' % '.'.join([str(x) for x in __version__]))

    if min_python_version < (2, 4):
        code_sink.writeln(r'''
#if PY_VERSION_HEX < 0x020400F0

#define PyEval_ThreadsInitialized() 1

#define Py_CLEAR(op)				\
        do {                            	\
                if (op) {			\
                        PyObject *tmp = (PyObject *)(op);	\
                        (op) = NULL;		\
                        Py_DECREF(tmp);		\
                }				\
        } while (0)


#define Py_VISIT(op)							\
        do { 								\
                if (op) {						\
                        int vret = visit((PyObject *)(op), arg);	\
                        if (vret)					\
                                return vret;				\
                }							\
        } while (0)

#endif

''')

    if min_python_version < (2, 5):
        code_sink.writeln(r'''
#if PY_VERSION_HEX < 0x020500F0

typedef int Py_ssize_t;
# define PY_SSIZE_T_MAX INT_MAX
# define PY_SSIZE_T_MIN INT_MIN
typedef inquiry lenfunc;
typedef intargfunc ssizeargfunc;
typedef intobjargproc ssizeobjargproc;

#endif
''')

    if min_python_version < (2, 6):
        code_sink.writeln(r'''
#ifndef PyVarObject_HEAD_INIT
#define PyVarObject_HEAD_INIT(type, size) \
        PyObject_HEAD_INIT(type) size,
#endif
''')

    code_sink.writeln(r'''
#ifdef Py_LIMITED_API
#  define _TYPEDEC *
#else
#  define _TYPEDEC 
#endif

#ifdef Py_LIMITED_API
# define _TYPEREF
#else
# define _TYPEREF &
#endif

#ifdef Py_LIMITED_API
# define PBG_SETATTR(_type, _name, _value)  PyObject_SetAttrString((PyObject*) _type, (char *) _name, (PyObject*) _value);
#else
# define PBG_SETATTR(_type, _name, _value)  PyDict_SetItemString((PyObject*) _type.tp_dict, _name, (PyObject*) _value);
#endif

#if PY_VERSION_HEX >= 0x03000000
#if PY_VERSION_HEX >= 0x03050000 && !defined(Py_LIMITED_API)
typedef PyAsyncMethods* cmpfunc;
#else
typedef void* cmpfunc;
#endif
#define PyCObject_FromVoidPtr(a, b) PyCapsule_New(a, NULL, b)
#define PyCObject_AsVoidPtr(a) PyCapsule_GetPointer(a, NULL)
#define PyString_FromString(a) PyBytes_FromString(a)
#define Py_TPFLAGS_CHECKTYPES 0 /* this flag doesn't exist in python 3 */
#endif
''')


    code_sink.writeln(r'''
#if     __GNUC__ > 2
# define PYBINDGEN_UNUSED(param) param __attribute__((__unused__))
#elif     __GNUC__ > 2 || (__GNUC__ == 2 && __GNUC_MINOR__ > 4)
# define PYBINDGEN_UNUSED(param) __attribute__((__unused__)) param
#else
# define PYBINDGEN_UNUSED(param) param
#endif  /* !__GNUC__ */

#ifndef _PyBindGenWrapperFlags_defined_
#define _PyBindGenWrapperFlags_defined_
typedef enum _PyBindGenWrapperFlags {
   PYBINDGEN_WRAPPER_FLAG_NONE = 0,
   PYBINDGEN_WRAPPER_FLAG_OBJECT_NOT_OWNED = (1<<0),
} PyBindGenWrapperFlags;
#endif

''')

    

def mangle_name(name):
    """make a name Like<This,and,That> look Like__lt__This_and_That__gt__"""
    s = name.replace('<', '__lt__').replace('>', '__gt__').replace(',', '_')
    s = s.replace(' ', '_').replace('&', '__amp__').replace('*', '__star__')
    s = s.replace(':', '_')
    s = s.replace('(', '_lp_').replace(')', '_rp_')
    return s


def get_mangled_name(base_name, template_args):
    """for internal pybindgen use"""
    assert isinstance(base_name, string_types)
    assert isinstance(template_args, (tuple, list))

    if template_args:
        return '%s__lt__%s__gt__' % (mangle_name(base_name), '_'.join(
                [mangle_name(arg) for arg in template_args]))
    else:
        return mangle_name(base_name)


class SkipWrapper(Exception):
    """Exception that is raised to signal a wrapper failed to generate but
    must simply be skipped.
    for internal pybindgen use"""

def call_with_error_handling(callback, args, kwargs, wrapper,
                             exceptions_to_handle=(TypeConfigurationError,
                                                   CodeGenerationError,
                                                   NotSupportedError)):
    """for internal pybindgen use"""
    if settings.error_handler is None:
        return callback(*args, **kwargs)
    else:
        try:
            return callback(*args, **kwargs)
        except Exception:
            _, ex, _ = sys.exc_info()
            if isinstance(ex, exceptions_to_handle):
                dummy1, dummy2, traceback = sys.exc_info()
                if settings.error_handler.handle_error(wrapper, ex, traceback):
                    raise SkipWrapper
                else:
                    raise
            else:
                raise


def ascii(value):
    """
    ascii(str_or_unicode_or_None) -> str_or_None

    Make sure the value is either str or unicode object, and if it is
    unicode convert it to ascii.  Also, None is an accepted value, and
    returns itself.
    """
    if value is None:
        return value
    elif isinstance(value, string_types):
        return value
    elif isinstance(value, string_types):
        return value.encode('ascii')
    else:
        raise TypeError("value must be str or ascii string contained in a unicode object")


def param(*args, **kwargs):
    """
    Simplified syntax for representing a parameter with delayed lookup.
    
    Parameters are the same as L{Parameter.new}.
    """
    return (args + (kwargs,))


def retval(*args, **kwargs):
    """
    Simplified syntax for representing a return value with delayed lookup.
    
    Parameters are the same as L{ReturnValue.new}.
    """
    return (args + (kwargs,))


def parse_param_spec(param_spec):
    if isinstance(param_spec, tuple):
        assert len(param_spec) >= 2
        if isinstance(param_spec[-1], dict):
            kwargs = param_spec[-1]
            args = param_spec[:-1]
        else:
            kwargs = dict()
            args = param_spec
    else:
        raise TypeError("Could not parse `%r' as a Parameter" % param_spec)
    return args, kwargs


def parse_retval_spec(retval_spec):
    if isinstance(retval_spec, tuple):
        assert len(retval_spec) >= 1
        if isinstance(retval_spec[-1], dict):
            kwargs = retval_spec[-1]
            args = retval_spec[:-1]
        else:
            kwargs = dict()
            args = retval_spec
    elif isinstance(retval_spec, string_types):
        kwargs = dict()
        args = (retval_spec,)
    else:
        raise TypeError("Could not parse `%r' as a ReturnValue" % retval_spec)
    return args, kwargs


def eval_param(param_value, wrapper=None):
    if isinstance(param_value, Parameter):
        return param_value
    else:
        args, kwargs = parse_param_spec(param_value)
        return call_with_error_handling(Parameter.new, args, kwargs, wrapper,
                                        exceptions_to_handle=(TypeConfigurationError,
                                                              NotSupportedError,
                                                              TypeLookupError))


def eval_retval(retval_value, wrapper=None):
    if isinstance(retval_value, ReturnValue):
        return retval_value
    else:
        args, kwargs = parse_retval_spec(retval_value)
        return call_with_error_handling(ReturnValue.new, args, kwargs, wrapper,
                                        exceptions_to_handle=(TypeConfigurationError,
                                                              NotSupportedError,
                                                              TypeLookupError))

