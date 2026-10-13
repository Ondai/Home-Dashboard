// Optional: puts the Google Tasks lists of one Google account (a shared family account works well)
// on the dashboard's to-do list, and lets the dashboard check them off, add, edit and delete them.
//
// Setup (the steps under Settings > To-dos > Google Tasks, on a phone, walk through it): signed in to
// that account, make a new project at script.new and paste this in. Under Services, add the Google
// Tasks API. Then Deploy > New deployment > Web app, with Execute as: Me and Who has access: Anyone,
// and paste the web app link into Settings. After changing this code, redeploy (Deploy > Manage
// deployments > edit > Version: New version) so the link stays the same.
//
// The first dashboard to connect is remembered, and from then on the link only works for it. To
// connect a different one (or the same one after resetting it), run forgetDashboard once from the
// editor: pick it next to Run, then click Run.

var DONE_DAYS = 31; // checked-off to-dos are sent this long, for the dashboard's "Done lately"

function forgetDashboard() {
  PropertiesService.getScriptProperties().deleteProperty('dashboardKey');
}

// Opening the link in a browser shows this, which confirms it's deployed
function doGet() {
  return ContentService.createTextOutput('This link is for the Home Dashboard. Paste it into Settings > To-dos > Google Tasks.');
}

function doPost(e) {
  var result;
  try {
    var request = JSON.parse(e.postData.contents);
    checkKey(request.key);
    result = handle(request);
  } catch (err) {
    result = { error: String(err && err.message || err) };
  }
  return ContentService.createTextOutput(JSON.stringify(result)).setMimeType(ContentService.MimeType.JSON);
}

function checkKey(key) {
  if (!key) throw new Error('missing key');
  var props = PropertiesService.getScriptProperties();
  var saved = props.getProperty('dashboardKey');
  if (!saved) {
    props.setProperty('dashboardKey', key); // the first dashboard to connect
  } else if (saved !== key) {
    throw new Error('this link is connected to a different dashboard (run forgetDashboard in the script to reset it)');
  }
}

// Every action answers with all the lists and to-dos, so the dashboard is up to date in one round trip
function handle(request) {
  var list = request.list, id = request.id, created = null;
  switch (request.action) {
    case 'read':
      break;
    case 'add':
      created = Tasks.Tasks.insert(fields({}, request), list).id;
      break;
    case 'edit':
      var task = Tasks.Tasks.get(list, id);
      if (request.toList && request.toList !== list) {
        // Moved to someone else's list: a copy there, then the original goes
        created = Tasks.Tasks.insert(fields({ status: task.status }, request), request.toList).id;
        Tasks.Tasks.remove(list, id);
      } else {
        Tasks.Tasks.update(fields(task, request), list, id);
      }
      break;
    case 'done':
      Tasks.Tasks.patch({ status: 'completed' }, list, id);
      break;
    case 'undone':
      Tasks.Tasks.patch({ status: 'needsAction', completed: null }, list, id);
      break;
    case 'delete':
      Tasks.Tasks.remove(list, id);
      break;
    default:
      throw new Error('unknown action ' + request.action);
  }
  var all = readAll();
  all.created = created;
  return all;
}

// Title, notes and due date from the dashboard; a missing due date clears it
function fields(task, request) {
  task.title = request.title;
  task.notes = request.notes || '';
  if (request.due) {
    task.due = request.due + 'T00:00:00.000Z'; // Google Tasks keeps dates, not times
  } else {
    delete task.due;
  }
  return task;
}

function readAll() {
  var lists = Tasks.Tasklists.list({ maxResults: 100 }).items || [];
  var since = new Date(Date.now() - DONE_DAYS * 86400000).toISOString();
  var tasks = [];
  lists.forEach(function (list) {
    var open = everyPage(list.id, { showCompleted: false });
    var done = everyPage(list.id, { showCompleted: true, showHidden: true, completedMin: since });
    open.concat(done.filter(function (t) { return t.status === 'completed'; })).forEach(function (t) {
      if (t.parent || t.deleted || !t.title) return; // sub-tasks and blank ones aren't shown
      tasks.push({
        id: t.id,
        list: list.id,
        title: t.title,
        notes: t.notes || '',
        due: t.due ? t.due.slice(0, 10) : null,
        completed: t.status === 'completed' ? t.completed : null
      });
    });
  });
  return { lists: lists.map(function (l) { return { id: l.id, title: l.title }; }), tasks: tasks };
}

function everyPage(listId, options) {
  var items = [], page;
  options.maxResults = 100;
  do {
    page = Tasks.Tasks.list(listId, options);
    items = items.concat(page.items || []);
    options.pageToken = page.nextPageToken;
  } while (options.pageToken);
  return items;
}
