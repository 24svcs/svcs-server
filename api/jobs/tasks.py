from celery import shared_task
from time import sleep

@shared_task
def notify_customers(message):
    print("Sending 10k emails")
    sleep(10)
    print("Emails were sent")