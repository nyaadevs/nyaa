from flask_sqlalchemy import Pagination, BaseQuery
from flask import abort


def paginate_faste(self, page=1, per_page=50, max_page=None, step=5):
    if page < 1:
        abort(404)

    if max_page and page > max_page:
        abort(404)

    items = self.limit(per_page).offset((page - 1) * per_page).all()

    if not items and page != 1:
        abort(404)

    # No need to count if there are fewer items than we expected.
    if len(items) < per_page or not step:
        total = (page - 1) * per_page + len(items)
    else:
        if max_page:
            total = self.order_by(None).limit(per_page * min((page + step), max_page)).count()
        else:
            total = self.order_by(None).limit(per_page * (page + step)).count()

    return Pagination(self, page, per_page, total, items)


BaseQuery.paginate_faste = paginate_faste
