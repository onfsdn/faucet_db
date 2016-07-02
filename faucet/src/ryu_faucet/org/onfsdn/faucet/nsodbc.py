"""docstring for module"""

COUCHDB = 'couchdb'
LOCALHOST = 'localhost'

class NsOdbc(object):
    """docstring for nsodbc"""
    def __init__(self):
        self.couchdb = None
        self.version = '1.0'

    def connect(self, *conn_string, **kwargs):
        """docstring"""
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
        """docstring"""
        return self.version

def todict(conn_string, kwargs):
    """docstring"""
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
    """docstring for connection"""
    def __init__(self, conn, credentials):
        self.conn = conn
        self.conn.resource.credentials = credentials
        self.database = None

    def create(self, db_name):
        """docstring"""
        self.database = self.conn.create(db_name)
        return self

    def insert_update_doc(self, doc, update_key):
        """docstring"""
        try:
            doc_id, doc_rev = self.database.save(doc)
            return doc_id
        except Exception, e:
            l_doc = self.database.get(doc['_id'])
            l_doc[update_key] = doc[update_key]
            self.database.save(l_doc)

    def get_docs(self, view_url, key):
        """docstring"""
        view_results = self.database.view(view_url, key=key)
        return view_results.rows

    def delete_doc(self, doc_id):
    	"""delete document"""
    	doc = self.database.get(doc_id)
    	self.database.delete(doc)

    def __getitem__(self, key):
        """docstring"""
        self.database = self.conn[key]
        return self


def nsodbc_factory():
    """factory method"""
    return NsOdbc()

if __name__ == '__main__':
#Testing
    ns_odbc = NsOdbc()
    conn = ns_odbc.connect('driver=couchdb;server=localhost;' + \
                    'uid=root;pwd=admin')
    try:
        db = conn.create('test')
    except Exception, e:
        db = conn['test']
        if not db:
            raise e
    j = {'_id': 'ham', 'abcd':'harshad11'}
    db.insert_update_doc(j, 'abcd')
    db.delete_doc('ham')
    j = {'_id': 'ham1', 'abcd':'harshad11'}
    db.insert_update_doc(j, 'abcd')
    # rows = db.get_docs('_design/docs/_view/apps', 'a')
    # print rows
