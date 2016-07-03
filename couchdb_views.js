/*
Collection of views
*/

/*
View url: _design/switches/_view/switch
Purpose: Getting switch ids
Databse: switches
*/
function(doc) {
	emit(doc._id, doc);
}

/*
View url: _design/flows/_view/flow
Purpose: Getting flow ids
Database: flows
*/
function(doc) {
	emit(doc._id, doc);
}

/*
View_url: _design/tags/_view/tags
Purpose: Getting Flows according to tags
Database: tags
*/
function(doc) {
	if(doc.tags){
		for(tag in doc.tags){
  		emit(doc.tags[tag], doc);
	}
}
