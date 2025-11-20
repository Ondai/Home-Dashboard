function doGet(e) {
  var callback = e.parameter.callback;
  var now = new Date();
  
  // Create date objects for Today, Tomorrow, and Day After Tomorrow
  var today = new Date(now);
  var tomorrow = new Date(now);
  tomorrow.setDate(today.getDate() + 1);
  var dayAfterTomorrow = new Date(now);
  dayAfterTomorrow.setDate(today.getDate() + 2);

  // Helper function to get events for a specific date
  function getEventsForDate(dateObj) {
    var eventsList = [];
    var calendars = CalendarApp.getAllCalendars();
    
    calendars.forEach(function(cal) {
      var events = cal.getEventsForDay(dateObj);
      events.forEach(function(event) {
        var isAllDayEvent = false;
        var startTime = event.getStartTime();
        
        // Check for all-day flags or midnight start times
        if (typeof event.isAllDay === 'function' && event.isAllDay()) {
          isAllDayEvent = true;
        }
        if (startTime.getHours() === 0 && startTime.getMinutes() === 0) {
           isAllDayEvent = true;
        }
        
        eventsList.push({
          title: event.getTitle(),
          startTime: startTime,
          isAllDay: isAllDayEvent
        });
      });
    });

    // Sort: All-day first, then by time
    eventsList.sort(function(a, b) {
      if (a.isAllDay && !b.isAllDay) return -1;
      if (!a.isAllDay && b.isAllDay) return 1;
      return new Date(a.startTime) - new Date(b.startTime);
    });

    // Format
    return eventsList.map(function(event) {
      return {
        title: event.title,
        time: event.isAllDay ? "All Day" : new Date(event.startTime).toLocaleTimeString('en-US', {
          hour: 'numeric',
          minute: '2-digit'
        })
      };
    });
  }

  // Build the response object
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

  var jsonOutput = JSON.stringify(responseData);
  var response = callback + '(' + jsonOutput + ')';

  return ContentService.createTextOutput(response)
    .setMimeType(ContentService.MimeType.JAVASCRIPT);
}