from django.core.management.base import BaseCommand
from human_resources.models import Attendance
from human_resources.utils.attendance_utils import verify_and_fix_late_attendance
from django.utils.translation import gettext as _

class Command(BaseCommand):
    help = 'Verify and fix attendance records that were wrongfully marked as late'

    def add_arguments(self, parser):
        parser.add_argument(
            '--attendance-id',
            type=str,
            help='Specific attendance ID to fix'
        )
        parser.add_argument(
            '--all',
            action='store_true',
            help='Check all late attendance records'
        )

    def handle(self, *args, **options):
        if not options['attendance_id'] and not options['all']:
            self.stdout.write(self.style.ERROR('Please provide either --attendance-id or --all'))
            return

        if options['attendance_id']:
            # Fix specific attendance
            was_fixed, message = verify_and_fix_late_attendance(options['attendance_id'])
            if was_fixed:
                self.stdout.write(self.style.SUCCESS(message))
            else:
                self.stdout.write(self.style.WARNING(message))
        else:
            # Fix all late attendances
            late_attendances = Attendance.objects.filter(status=Attendance.ATTENDANCE_LATE)
            fixed_count = 0
            total_count = late_attendances.count()

            self.stdout.write(f"Found {total_count} late attendance records to check...")

            for attendance in late_attendances:
                was_fixed, message = verify_and_fix_late_attendance(attendance.id)
                if was_fixed:
                    fixed_count += 1
                    self.stdout.write(self.style.SUCCESS(
                        f"Fixed attendance {attendance.id}: {message}"
                    ))
                else:
                    self.stdout.write(self.style.WARNING(
                        f"Attendance {attendance.id}: {message}"
                    ))

            self.stdout.write(self.style.SUCCESS(
                f"\nProcess completed: Fixed {fixed_count} out of {total_count} late attendance records"
            )) 