#include <Python.h>
#include <ftt.h>

typedef struct ET_descriptor 
{
	ftt_descriptor ftt_desc;
	char *buffer;
	int block_size;
	char *bufptr;		/* buffer to build output block - write only */
        int hadeof;		/* seen an eof on this file - read only */
        long filesize;		/* # of bytes */
} ET_descriptor;

#define CKALLOC(malloc_call) if ( !(malloc_call) ) {PyErr_NoMemory(); return NULL;} 

/*
 An error reporter which produces an error string and raises an exception for python
*/
#ifdef HAVE_STDARG_PROTOTYPES
static PyObject *
raise_ftt_exception(char * location,  ET_descriptor *ET_desc, ...)
#else
static PyObject *
raise_ftt_exception(location, ET_desc, va_alist)
	char *location;
	ET_descriptor *ET_desc;
        va_dcl;
#endif
{
/*  dealloc and raise exception fix */
  printf("Error in ETAPE module at %s - FTT reports: %s\n", location, ftt_get_error(ET_desc->ftt_desc));
  return NULL;
}

/*
  Module description
*/
static char ETape_Doc[] =  "ETape is a module which interfaces to ENSTORE TAPE drives";

/*
   Method implementations
*/

/* = = = = = = = = = = = = = = -  ET_OpenRead  = = = = = = = = = = = = = = - */

static char ET_OpenRead_Doc[] = "Open a tape drive for reading";

static PyObject* ET_OpenRead(PyObject *self, PyObject *args)
{
  char *fname;
  int position;
  int sts;
  long *thisET;
  PyObject *ETobj;
  ET_descriptor *ET_desc;
/*
	Allocate an ETApe desciptor block
*/
  CKALLOC( ET_desc = (ET_descriptor*)malloc (sizeof(ET_descriptor) ) ); 
/*
	Parse the arguments 
*/
  PyArg_ParseTuple(args, "sii", &fname, &position, &ET_desc->block_size);
/*
	Allocate a read buffer
*/
  CKALLOC( ET_desc->buffer = malloc( ET_desc->block_size ) );

  ET_desc->hadeof = 0;
  ET_desc->filesize = 0;
/*
	Open the FTT way
*/
  ET_desc->ftt_desc = ftt_open(fname, FTT_RDONLY);
  sts = ftt_open_dev(ET_desc->ftt_desc);
  if (!sts) 
    return raise_ftt_exception("ET_OpenRead_opendev", ET_desc, "%s", fname);
/*
	Position to the file, if backwards then skip back forward to BOF
*/
  if (position != 0) 
  {
    sts = ftt_skip_fm(ET_desc->ftt_desc, position);
    if (sts)
      return raise_ftt_exception("ET_OpenRead_skipfm", ET_desc, "%s", fname);
  }
  if (position < 0)
  {
    sts = ftt_skip_fm(ET_desc->ftt_desc, 1);
    if (sts)
      return raise_ftt_exception("ET_OpenRead_NegForward", ET_desc, "%s", fname);
  }
  
  return Py_BuildValue("l",(long int)ET_desc);}
/* = = = = = = = = = = = = = = -  ET_ReadBlock  = = = = = = = = = = = = = = - */

static char ET_ReadBlock_Doc[] = "Read a block from tape";

static PyObject* ET_ReadBlock(PyObject *self, PyObject *args)
{
  ET_descriptor *ET_desc;
  int len;
  int datalen;
  int bytesleft;
  char *returnptr;
/*
	Get the arguments
*/
  PyArg_ParseTuple(args, "l|i", (long int *)&ET_desc);
  if (ET_desc->hadeof)    /* this is not ftt exception fix */
    return raise_ftt_exception("ET_ReadBlock_ReadAfterEof", ET_desc);
  len=ftt_read(ET_desc->ftt_desc, ET_desc->buffer, ET_desc->block_size);
  if (len < 0)
     return raise_ftt_exception("ET_ReadBlock", ET_desc);
  if (len == 0)
     ET_desc->hadeof = 1;
  ET_desc->filesize += len;
  return Py_BuildValue("s#", ET_desc->buffer, len);
}
/* = = = = = = = = = = = = = = -  ET_CloseRead  = = = = = = = = = = = = = = - */

static char ET_CloseRead_Doc[] = "Close an input tape";

static PyObject* ET_CloseRead(PyObject *self, PyObject *args)
{
  ET_descriptor *ET_desc;
  ftt_stat_buf   stbuff;
  int sts;
  PyObject *ErrDict;
/*
	Get the arguements
*/
  PyArg_ParseTuple(args, "l", (long int *)&ET_desc);
/*
	Get the tape stats from FTT
*/
  stbuff = ftt_alloc_stat();
  sts=ftt_get_stats(ET_desc->ftt_desc, stbuff);
  if (sts <0)
    return raise_ftt_exception("ET_CloseRead_stats", ET_desc);
  ErrDict = Py_BuildValue ("(s,s,s,i)", 
     ftt_extract_stats(stbuff,FTT_REMAIN_TAPE),
     ftt_extract_stats(stbuff,FTT_N_READS),
     ftt_extract_stats(stbuff,FTT_READ_ERRORS),
     ET_desc->filesize
    );
  sts=ftt_free_stat(stbuff);
/*
	Close the ftt file
*/
  sts=ftt_close(ET_desc->ftt_desc);
  if (sts <0)
    return raise_ftt_exception("ET_CloseRead", ET_desc);
/*
	Free the memory we allocated
*/
  free(ET_desc->buffer);
  free(ET_desc);
  
  return ErrDict;
}
/* = = = = = = = = = = = = = = -  ET_OpenWrite  = = = = = = = = = = = = = = - */

static char ET_OpenWrite_Doc[] = "Open a tape drive for writing";

static PyObject* ET_OpenWrite(PyObject *self, PyObject *args)
{
  char *fname;
  ET_descriptor *ET_desc; 
  int sts;
  int eod;
/*
	Get the arguements
*/
  CKALLOC( ET_desc = (ET_descriptor*)malloc (sizeof(ET_descriptor)) );
  PyArg_ParseTuple(args, "sii", &fname, &eod, &ET_desc->block_size);
/*
	Allocate a write buffer
*/
  CKALLOC( ET_desc->buffer = malloc( ET_desc->block_size ) );
  ET_desc->bufptr =  ET_desc->buffer;
  ET_desc->filesize =0;
/*
	Open the ftt file
*/
  ET_desc->ftt_desc = ftt_open(fname, FTT_RDWR);
  sts = ftt_open_dev(ET_desc->ftt_desc);
  if (!sts)
    return raise_ftt_exception("ET_OpenWrite", ET_desc, "%s", fname);
  if (eod != 0)
  {
    sts = ftt_skip_fm(ET_desc->ftt_desc, eod);
    if (sts)
      return raise_ftt_exception("ET_OpenWrite_skipfm", ET_desc, "%s", fname);
  }
/*
	Return The ETape descriptor
*/
  return Py_BuildValue("l",(long)ET_desc);
}
/* = = = = = = = = = = = = = = -  ET_WriteBlock  = = = = = = = = = = = = = = - */

static char ET_WriteBlock_Doc[] = "Write a block to tape";

static PyObject* ET_WriteBlock(PyObject *self, PyObject *args)
{
  ET_descriptor *ET_desc;
  int sts;
  char *data_buff;
  int length;
  int partlen;

  PyArg_ParseTuple(args, "ls#", &ET_desc, &data_buff, &length);
  ET_desc->filesize += length;
  while (length > 0)
  {
    if (ET_desc->bufptr + length < ET_desc->buffer + ET_desc->block_size) 
    {
      memcpy(ET_desc->bufptr, data_buff, length);
      ET_desc->bufptr += length;
      break;
    } else {
      partlen = ET_desc->buffer + ET_desc->block_size - ET_desc->bufptr;
      memcpy(ET_desc->bufptr, data_buff, partlen);
      
      sts=ftt_write(ET_desc->ftt_desc,  ET_desc->buffer, ET_desc->block_size);
      if (sts != length)
         return raise_ftt_exception("ET_WriteBlock", ET_desc);
      ET_desc->bufptr = ET_desc->buffer;
      length -= partlen;
      data_buff += partlen;
    }
  }
  return Py_BuildValue("i",0);
}
/* = = = = = = = = = = = = = = -  ET_CloseWrite  = = = = = = = = = = = = = = - */

static char ET_CloseWrite_Doc[] = "Close an output tape";

static PyObject* ET_CloseWrite(PyObject *self, PyObject *args)
{
  ET_descriptor *ET_desc;
  ftt_stat_buf   stbuff;
  int sts;
  PyObject *ErrDict;
  int partlen;
/*
        Parse the arguments
*/
  PyArg_ParseTuple(args, "l", (long int *)&ET_desc);
/*
	Write unwritten buffer
*/
  partlen = ET_desc->bufptr - ET_desc->buffer;
  if (partlen > 0)
  {
    sts=ftt_write(ET_desc->ftt_desc,  ET_desc->buffer, partlen);
    if (sts != partlen)
        return raise_ftt_exception("ET_CloseWrite_Block", ET_desc);
  }
/*
	Get the tape stats
*/
  sts=ftt_write2fm(ET_desc->ftt_desc);
  if (sts <0 )
      return raise_ftt_exception("ET_CloseWrite_FM", ET_desc);
  sts=ftt_skip_fm(ET_desc->ftt_desc,-1);
  if (sts <0 )
      return raise_ftt_exception("ET_CloseWrite_MB", ET_desc);

  stbuff = ftt_alloc_stat();
  sts=ftt_get_stats(ET_desc->ftt_desc, stbuff);
  if (sts < 0)
    return raise_ftt_exception("ET_ClosePartial", ET_desc);

  ErrDict = Py_BuildValue ("(s,s,s,i)", 
    ftt_extract_stats(stbuff,FTT_REMAIN_TAPE),
    ftt_extract_stats(stbuff,FTT_N_WRITES),
    ftt_extract_stats(stbuff,FTT_WRITE_ERRORS),
    ET_desc->filesize
    );
/*
	Close the drive
*/
  sts=ftt_close(ET_desc->ftt_desc);
  if (sts < 0)
    return raise_ftt_exception("ET_CloseWrite", ET_desc);
/*
	Free the memory
*/
  free(ET_desc->buffer);
  free(ET_desc); 

  return ErrDict;
}
/* = = = = = = = = = = = = = = -  Python Module Definitions = = = = = = = = = = = = = = - */

/*
   Module Methods table. 

   There is one entry with four items for for each method in the module

   Entry 1 - the method name as used  in python
         2 - the c implementation function
         3 - flags 
         4 - method documentation string
*/
static PyMethodDef ETape_Methods[] = {
  { "ET_OpenWrite",  ET_OpenWrite,  1, ET_OpenWrite_Doc},
  { "ET_OpenRead",   ET_OpenRead,   1, ET_OpenRead_Doc},
  { "ET_WriteBlock", ET_WriteBlock, 1, ET_WriteBlock_Doc},
  { "ET_ReadBlock",  ET_ReadBlock,  1, ET_ReadBlock_Doc},
  { "ET_CloseRead",  ET_CloseRead,  1, ET_CloseRead_Doc},
  { "ET_CloseWrite", ET_CloseWrite, 1, ET_CloseWrite_Doc},
  { 0, 0}        /* Sentinel */
};

/*
   Module initialization.   Python call the entry point init<module name>
   when the module is imported.  This should the only non-static entry point
   so it is exported to the linker.

   The Py_InitModule4 is not in the python 1.5 documentation but is copied
   from the oracle module.  It extends Py_InitModule with documentation
   and seems useful.

   First argument must be a the module name string.

   Seond        - a list of the module methods

   Third	- a doumentation string for the module
  
   Fourth & Fifth - see Python/modsupport.c

*/
void initETape()
{
  (void) Py_InitModule4("ETape", ETape_Methods, ETape_Doc, 
                               (PyObject*)NULL,PYTHON_API_VERSION);
}
