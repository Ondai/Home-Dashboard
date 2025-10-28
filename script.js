document.addEventListener('alpine:init', () => {
    Alpine.data('countdownApp', () => ({
        // --- DATA ---
        events: Alpine.store('events', []),
        showModal: false,
        newEventTitle: '',
        newEventDate: '',

        // --- METHODS ---
        init() {
            setInterval(() => {
                this.updateTimers();
            }, 1000); 

            const grid = document.getElementById('countdownGrid');
            new Sortable(grid, {
                animation: 150,
                onEnd: (evt) => {
                    const movedItem = this.events.splice(evt.oldIndex, 1)[0];
                    this.events.splice(evt.newIndex, 0, movedItem);
                },
            });
        },

        updateTimers() {
            this.events.forEach(event => {
                // **THE FIX IS ON THIS LINE**
                // We add 'T00:00:00' to force the date to be interpreted in the user's local timezone.
                const targetDate = new Date(event.date + 'T00:00:00').getTime();
                
                const now = new Date().getTime();
                const distance = targetDate - now;

                if (distance < 0) {
                    event.days = 0;
                    return;
                }
                
                event.days = Math.ceil(distance / (1000 * 60 * 60 * 24));
            });
        },

        addEvent() {
            if (!this.newEventTitle || !this.newEventDate) {
                alert('Please fill in both the title and the date.');
                return;
            }

            const newEvent = {
                id: Date.now(),
                title: this.newEventTitle,
                date: this.newEventDate,
                days: 0 
            };
            
            this.events = [...this.events, newEvent];

            this.newEventTitle = '';
            this.newEventDate = '';
            this.showModal = false;
        },

        removeEvent(eventId) {
            this.events = this.events.filter(event => event.id !== eventId);
        }
    }));
});