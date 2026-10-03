// Optional alternative to iCal links: a Google Apps Script web app that returns the next three
// days of events from every calendar in the Google account. Deploy it as a web app (Execute as:
// Me; Who has access: Anyone) and paste its URL into Settings > Advanced settings on the dashboard.
// After changing this code, redeploy (Deploy > Manage deployments > edit > Version: New version)
// so the URL stays the same.
function doGet(e) {
  var callback = e.parameter.callback || 'callback';
  var now = new Date();

  var today = new Date(now);
  var tomorrow = new Date(now);
  tomorrow.setDate(today.getDate() + 1);
  var dayAfterTomorrow = new Date(now);
  dayAfterTomorrow.setDate(today.getDate() + 2);

  function getEventsForDate(dateObj) {
    var eventsList = [];
    CalendarApp.getAllCalendars().forEach(function(cal) {
      cal.getEventsForDay(dateObj).forEach(function(event) {
        var startTime = event.getStartTime();
        // Some all-day events only show as starting at midnight
        var isAllDay = event.isAllDayEvent() || (startTime.getHours() === 0 && startTime.getMinutes() === 0);
        eventsList.push({ title: event.getTitle(), startTime: startTime, endTime: event.getEndTime(), isAllDay: isAllDay });
      });
    });

    // All-day first, then by time
    eventsList.sort(function(a, b) {
      if (a.isAllDay !== b.isAllDay) return a.isAllDay ? -1 : 1;
      return a.startTime - b.startTime;
    });

    return eventsList.map(function(event) {
      return {
        title: event.title,
        time: event.isAllDay ? 'All Day' : event.startTime.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' }),
        // Full times let the dashboard hide finished events and mark multi-day ones (day 2/3)
        start: event.startTime.toISOString(),
        end: event.endTime.toISOString(),
        allDay: event.isAllDay
      };
    });
  }

  var responseData = {
    today: getEventsForDate(today),
    tomorrow: getEventsForDate(tomorrow),
    dayAfterTomorrow: getEventsForDate(dayAfterTomorrow),
    dates: {
      today: today.getDate(),
      tomorrow: tomorrow.getDate(),
      dayAfterTomorrow: dayAfterTomorrow.getDate(),
      dayAfterTomorrowName: dayAfterTomorrow.toLocaleDateString('en-US', { weekday: 'long' })
    }
  };

  return ContentService.createTextOutput(callback + '(' + JSON.stringify(responseData) + ')')
    .setMimeType(ContentService.MimeType.JAVASCRIPT);
}
