"""docstring for module"""

COUCHDB = 'couchdb'
LOCALHOST = 'localhost'

class NsOdbc(object):
    """An abstraction layer to make api calls to a non relational database.

    Currently the API provided is:
    connect
    create
    get_doc
    insert_update_doc
    delete_doc
    """
    def __init__(self):
        self.couchdb = None
        self.version = '1.0'

    def connect(self, *conn_string, **kwargs):
        """Returns a connection object required to make further operations"""
        conn_dict = {}
        conn_dict = todict(conn_string, kwargs)

        if conn_dict['driver'] == COUCHDB:
            try:
                import couchdb
                self.couchdb = couchdb
            except ImportError, e:
                raise e
            if conn_dict['server'] == LOCALHOST:
                cnxn = ConnectionCouch(couchdb.Server(),
                (conn_dict['uid'], conn_dict['pwd']))
            else:
                cnxn = ConnectionCouch(couchdb.Server(),
                (conn_dict['uid'], conn_dict['pwd']))
            return cnxn

    def get_attributes(self):
        """Returns API version"""
        return self.version

def todict(conn_string, kwargs):
    """Converts the input connection string into a dictionary"""
    ret = {}
    conn_dict = {}
    for c_str in conn_string:
        arr = c_str.split(';')
        for elem in arr:
            temp = elem.split('=')
            ret[temp[0]] = temp[1]

    conn_dict = ret.copy()
    conn_dict.update(kwargs)
    return conn_dict

class ConnectionCouch(object):
    """Connection class exposing the API"""
    def __init__(self, conn, credentials):
        self.conn = conn
        self.conn.resource.credentials = credentials
        self.database = None

    def create(self, db_name):
        """Create a doc in the database"""
        self.database = self.conn.create(db_name)
        return self

    def insert_update_doc(self, doc, update_key):
        """Insert or update a document
        
        For updating, a key has to provided against which a document will be updated
        """
        try:
            doc_id, doc_rev = self.database.save(doc)
            return doc_id
        except Exception, e:
            l_doc = self.database.get(doc['_id'])
            l_doc[update_key] = doc[update_key]
            doc_id, doc_rev = self.database.save(l_doc)
            return doc_id

    def get_docs(self, view_url, key):
        """Select docs

        A view url is used as select query with the key as a where condition
        """
        view_results = self.database.view(view_url, key=key)
        return view_results.rows

    def delete_doc(self, doc_id):
    	"""Delete document based on the doc id"""
    	doc = self.database.get(doc_id)
    	self.database.delete(doc)

    def __getitem__(self, key):
        """Returns the database for this particular connection"""
        self.database = self.conn[key]
        return self


def nsodbc_factory():
    """factory method"""
    return NsOdbc()