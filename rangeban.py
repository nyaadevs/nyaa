#!/usr/bin/env python3

import sys

import click

from nyaa import create_app, models
from nyaa.extensions import db


def is_cidr_valid(c):
    '''Checks whether a CIDR range string is valid.'''
    try:
        subnet, mask = c.split('/')
    except ValueError:
        return False
    if int(mask) < 1 or int(mask) > 32:
        return False
    try:
        bs = subnet.split('.')
    except ValueError:
        return False
    if len(bs) != 4:
        return False
    for b in bs:
        if int(b) > 255 or int(b) < 0:
            return False
    return True


def check_str(b):
    '''Returns a checkmark or cross depending on the condition.'''
    return '\u2713' if b else '\u2717'


@click.group()
def rangeban():
    global app
    app = create_app('config')


@rangeban.command()
@click.option('--temp/--no-temp', help='Mark this entry as one that may be '
              'cleaned out occasionally.', default=False)
@click.argument('cidrrange')
def ban(temp, cidrrange):
    if not is_cidr_valid(cidrrange):
        click.secho('{} is not of the format xxx.xxx.xxx.xxx/xx.'
                    .format(cidrrange), err=True, fg='red')
        sys.exit(1)
    with app.app_context():
        ban = models.RangeBan(cidr_string=cidrrange, temp=temp)
        db.session.add(ban)
        db.session.commit()
        click.echo('Added {} for {}.'.format('temp ban' if temp else 'ban',
                                             cidrrange))


@rangeban.command()
@click.argument('cidrrange')
def unban(cidrrange):
    if not is_cidr_valid(cidrrange):
        click.secho('{} is not of the format xxx.xxx.xxx.xxx/xx.'
                    .format(cidrrange), err=True, fg='red')
        sys.exit(1)
    with app.app_context():
        # Dunno why this wants _cidr_string and not cidr_string, probably
        # due to this all being a janky piece of shit.
        bans = models.RangeBan.query.filter(
            models.RangeBan._cidr_string == cidrrange).all()
        if len(bans) == 0:
            click.echo('Couldn\'t find that ban. :(')
        for b in bans:
            click.echo('Unbanned {}'.format(b.cidr_string))
            db.session.delete(b)
        db.session.commit()


@rangeban.command()
def list():
    with app.app_context():
        bans = models.RangeBan.query.all()
        if len(bans) == 0:
            click.echo('No bans. :(')
        else:
            click.secho('ID     CIDR Range         Enabled Temp', bold=True)
            for b in bans:
                click.echo('{0: <6} {1: <18} {2: <7} {3: <4}'
                           .format(b.id, b.cidr_string,
                                   check_str(b.enabled),
                                   check_str(b.temp)))

@rangeban.command()
@click.argument('id', type=int)
@click.argument('status')
def enabled(id, status):
    yeses = ['true', '1', 'yes', '\u2713']
    noses = ['false', '0', 'no', '\u2717']
    if status.lower() in yeses:
        set_to = True
    elif status.lower() in noses:
        set_to = False
    else:
        click.secho('Please choose one of {} or {}.'
                    .format(yeses, noses), err=True, fg='red')
        sys.exit(1)
    with app.app_context():
        ban = models.RangeBan.query.get(id)
        if not ban:
            click.secho('No ban with id {} found.'
                        .format(id), err=True, fg='red')
            sys.exit(1)
        ban.enabled = set_to
        db.session.add(ban)
        db.session.commit()
        click.echo('{} ban {} on {}.'.format('Enabled' if set_to else 'Disabled',
                                             id, ban._cidr_string))



if __name__ == '__main__':
    rangeban()
