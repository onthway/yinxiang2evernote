#!/usr/bin/env python
# coding: utf-8

import json
import os
import hashlib
import sys

from evernote.api.client import EvernoteClient
import evernote.edam.type.ttypes as Types
import evernote.edam.userstore.constants as UserStoreConstants
from evernote.edam.error.ttypes import EDAMUserException
from evernote.edam.error.ttypes import EDAMSystemException
from evernote.edam.error.ttypes import EDAMNotFoundException
from evernote.edam.error.ttypes import EDAMErrorCode
from evernote.edam.notestore import NoteStore
from evernote.edam.notestore.ttypes import NotesMetadataResultSpec


class EvernoteConnecter(object):
    # data_file_dict = {'sync_state': './data/sync_state.json'}

    def __init__(self, dev_token, service_host):
        self._connect_to_evernote(dev_token, service_host)
        self.data_file_dict = {'sync_state': './data/sync_state.json'}

    def data_file(self,file):
        return self.data_file_dict[file]

    def get_current_sync_state(self):
        note_store = self.client.get_note_store()
        currnet_sync_state = note_store.getSyncState()

        filename = self.data_file('sync_state')
        if not os.path.exists(os.path.dirname(filename)):
            try:
                os.makedirs(os.path.dirname(filename))
            except OSError as exc:  # Guard against race condition
                if exc.errno != errno.EEXIST:
                    raise
        with open(filename, "w") as f:
            json.dump(currnet_sync_state.__dict__, f)
        return currnet_sync_state.updateCount

    def get_last_update_count(self):
        #获取上一次同步状态
        if os.path.exists( self.data_file('sync_state')):
            last_sync_state = json.load(open(self.data_file('sync_state'),'r'))
            last_update_count = last_sync_state['updateCount']
            return last_update_count
        else:
            return 0

    def _connect_to_evernote(self, dev_token, service_host):
        user = None
        try:
            # client = EvernoteClient(token=devToken, service_host='app.yinxiang.com', sandbox=False)
            # print "host information:", dev_token, service_host
            self.client = EvernoteClient(token=dev_token, service_host=service_host, sandbox=False)
            self.user_store = self.client.get_user_store()
            # print "user_store"
            user = self.user_store.getUser()
            # print "user:", user
        except EDAMUserException as e:
            err = e.errorCode
            print("Error attempting to authenticate to Evernote: %s - %s" % (
            EDAMErrorCode._VALUES_TO_NAMES[err], e.parameter))
            return False
        except EDAMSystemException as e:
            err = e.errorCode
            print(
            "Error attempting to authenticate to Evernote: %s - %s" % (EDAMErrorCode._VALUES_TO_NAMES[err], e.message))
            sys.exit(-1)

        if user:
            print("Authenticated to evernote as user %s" % user.username)
            return True
        else:
            return False

    def _get_notebooks(self):
        note_store = self.client.get_note_store()
        notebooks = note_store.listNotebooks()
        return {n.name: n for n in notebooks}

    def _create_notebook(self, notebook):
        note_store = self.client.get_note_store()
        return note_store.createNotebook(notebook)

    def _update_notebook(self, notebook):
        note_store = self.client.get_note_store()
        note_store.updateNotebook(notebook)
        return

    def _check_and_make_notebook(self, notebook_name, stack=None):
        notebooks = self._get_notebooks()
        if notebook_name in notebooks:
            # Existing notebook, so just update the stack if needed
            notebook = notebooks[notebook_name]
            if stack:
                notebook.stack = stack
                self._update_notebook(notebook)
            return notebook
        else:
            # Need to create a new notebook
            notebook = Types.Notebook()
            notebook.name = notebook_name
            if stack:
                notebook.stack = stack
            notebook = self._create_notebook(notebook)
            return notebook

    def _create_evernote_note(self, notebook, filename):
        # Create the new note
        note = Types.Note()
        note.title = os.path.basename(filename)
        note.notebookGuid = notebook.guid
        note.content = '<?xml version="1.0" encoding="UTF-8"?><!DOCTYPE en-note SYSTEM "http://xml.evernote.com/pub/enml2.dtd">'
        note.content += '<en-note>My first PDF upload<br/>'

        # Calculate the md5 hash of the pdf
        md5 = hashlib.md5()
        with open(filename, 'rb') as f:
            pdf_bytes = f.read()
        md5.update(pdf_bytes)
        md5hash = md5.hexdigest()

        # Create the Data type for evernote that goes into a resource
        pdf_data = Types.Data()
        pdf_data.bodyHash = md5hash
        pdf_data.size = len(pdf_bytes)
        pdf_data.body = pdf_bytes

        # Add a link in the evernote boy for this content
        link = '<en-media type="application/pdf" hash="%s"/>' % md5hash
        note.content += link
        note.content += '</en-note>'

        # Create a resource for the note that contains the pdf
        pdf_resource = Types.Resource()
        pdf_resource.data = pdf_data
        pdf_resource.mime = "application/pdf"

        # Create a resource list to hold the pdf resource
        resource_list = []
        resource_list.append(pdf_resource)

        # Set the note's resource list
        note.resources = resource_list

        return note


    def upload_to_notebook(self, filename, notebookname):

        # Check if the evernote notebook exists
        print ("Checking for notebook named %s" % notebookname)
        notebook = self._check_and_make_notebook(notebookname, "my_stack")

        print("Uploading %s to %s" % (filename, notebookname))

        note = self._create_evernote_note(notebook, filename)

        # Store the note in evernote
        note_store = self.client.get_note_store()
        note = note_store.createNote(note)

    def copy_to_notebook(self, note, notebookname):

        # Check if the evernote notebook exists
        # print ("Checking for notebook named %s" % notebookname)
        notebook = self._check_and_make_notebook(notebookname, "0@@inbox")

        noteev = Types.Note()
        noteev.created = note.created
        noteev.notebookGuid = notebook.guid
        noteev.content = note.content
        noteev.title = note.title
        noteev.resources = note.resources
        print("Uploading [%s]... " % (noteev.title))

        # print "note:", note.title
        # Store the note in evernote
        try:
            note_store = self.client.get_note_store()
            note = note_store.createNote(noteev)
            # print "copy is ok!"
            return True
        except Exception, e:
            print "Can't upload the note! Exception: ", e
            return None

    def get_notes(self, note_count):
        note_store = self.client.get_note_store()
        noteFilter = NoteStore.NoteFilter(ascending=False, order= Types.NoteSortOrder.CREATED)
        spec = NotesMetadataResultSpec(includeTitle=True)
        try:
            notes = note_store.findNotes(noteFilter, 0, note_count)
            #notes = note_store.findNotesMetadata(note_store.token, noteFilter, 0, note_count, spec)
            if notes.totalNotes:
                print  "notes tota is ", notes.totalNotes
                return notes
        except Exception, e:
            print "Can't get notes ! Exception: ", e
            return None

    def get_content(self, note):
        note_store = self.client.get_note_store()
        content = note_store.getNoteContent(note.guid)
        if note.resources is not None:
            for res in note.resources:
                data = res.data
                data = yx.get_resouece(res.guid).data
                res.data = data

        return content

    def get_resouece(self, guid):
        note_store = self.client.get_note_store()
        content = note_store.getResource(guid, True, True, True, True)
        return content

    def delete_note(self,guid):
        note_store = self.client.get_note_store()
        note_store.deleteNote(guid)


if __name__ == '__main__':
    # authToken = "" # bypass the dev token prompt by populating this variable.
    # 填写你自行申请的 token 地址
    authToken_yinxiang = ""
    Host_yinxiang = "app.yinxiang.com"

    # authToken = "" # bypass the dev token prompt by populating this variable.
    authToken_evernote = ""
    Host_evernote = "www.evernote.com"

    yx = EvernoteConnecter(authToken_yinxiang, Host_yinxiang)
    ev = EvernoteConnecter(authToken_evernote, Host_evernote)

    last_update_count = yx.get_last_update_count()

    current_sync_count = yx.get_current_sync_state()

    if last_update_count >= current_sync_count:
        sys.exit(2)

    # notes_yx = Types.NoteList()
    notes_yx = yx.get_notes(100)
    for note in notes_yx.notes:

        note.content = yx.get_content(note)

        # print "content:", note.content
        if ev.copy_to_notebook(note, "yx2ev"):
            yx.delete_note(note.guid)
            print ("upload [%s] success !" % (note.title))
        else:
            print("upload [%s] is fail !" % (note.title))




