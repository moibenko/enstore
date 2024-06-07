%module checksum
%{
/* $Id$ */
#include "zlib.h"
#if !defined(__STDC_VERSION__) || ( __STDC_VERSION__ > 199409L )
#include <stdint.h>
#endif

unsigned long int adler32_o(unsigned long int crc, char *buf, int offset, int nbytes){
	return adler32(crc, buf+offset, nbytes);
}

%}

/* Include in the generated wrapper file */
%include "typemaps.i"

#ifdef SWIG_VERSION
/* SWIG_VERSION was first used in swig 1.3.11 and has hex value 0x010311. */

%{
#ifdef UINT32_MAX
   typedef uint32_t zint;
#else
   typedef unsigned int zint;
#endif
typedef long long off_t_2;
typedef unsigned char * cptr;
%}
/* Tell SWIG about it */
#ifdef UINT32_MAX
   typedef uint32_t zint;
#else
   typedef unsigned int zint;
#endif
typedef long long off_t_2;
typedef unsigned char * cptr;

%typemap(in) zint {
    if (PyLong_Check($input))
        $1 = (unsigned long) PyLong_AsUnsignedLong($input);
    else if (PyInt_Check($input))
        $1 = (unsigned long) PyInt_AsLong($input);
    else {
        PyErr_SetString(PyExc_TypeError, "expected integral type");
        return NULL;
    }
}
%typemap(out) zint {
        $result = PyLong_FromUnsignedLong((zint)$1);
}
%typemap(in) cptr {
  //        $1= PyBytes_AS_STRING($input);
  //$1 = PyBytes_AsBytes($input);
  $1 = PyBytes_AsString($input);
}
%typemap(in) off_t_2 {
    if (PyLong_Check($input))
        $1 = (long long) PyLong_AsLongLong($input);
    else if (PyInt_Check($input))
        $1 = (long long) PyInt_AsLong($input);
    else {
        PyErr_SetString(PyExc_TypeError, "expected integral type");
        return NULL;
    }
}
#else
/* No SWIG_VERSION defined means a version older than 1.3.11.  Here we only
 * care to differentiate between 1.3.x and 1.1.y, though an issue exists
 * for 1.3 versions with a patch level 10 or less. */

%{
/* Since SWIG 1.1 doesn't recognize "long long" as a data type, we
 * need to play some trickery to get it to work with large files.*/
#define double long long
%}

%typedef unsigned int zint;
%typedef char * cptr;
%typedef double off_t_2; /*Swig 1.1 doesn't have "long long" */

%{
/* Since SWIG 1.1 doesn't recognize "long long" as a data type, we
 * need to play some trickery to get it to work with large files.*/
#undef double
%}

%typemap(python,in) zint {
    if (PyLong_Check($source))
	$target= (unsigned long) PyLong_AsUnsignedLong($source);
    else if (PyInt_Check($source))
	$target= (unsigned long) PyInt_AsLong($source);
    else {
	PyErr_SetString(PyExc_TypeError, "expected integral type");
	return NULL;
    }
}
%typemap(python,out) zint {
	$target= PyLong_FromUnsignedLong((zint)$source);
}
%typemap(python, in) cptr{
        $target= PyString_AsString($source);
}
%typemap(python,in) off_t_2 {
    /* Since SWIG 1.1 doesn't recognize "long long" as a data type, we
     * need to play some trickery to get it to work with large files.
     * There is a C #define macro that sets off_t_2 to be long long. */
    if (PyLong_Check($source)) {
        $target = (long long) PyLong_AsLongLong($source);
    }	
    else if (PyInt_Check($source)) {
        $target = (long long) PyInt_AsLong($source);
    }
    else {
	PyErr_SetString(PyExc_TypeError, "expected integral type");
	return NULL;
    }
}
#endif

zint adler32(zint, cptr, int);

zint adler32_o(zint, cptr, int, int);

zint convert_0_adler32_to_1_adler32(zint crc, off_t_2 filesize);
